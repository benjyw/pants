# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional, Union

from pants.backend.python_new.subsystems import PythonSettings
from pants.engine.fs import PathGlobs
from pants.engine.intrinsics import path_globs_to_digest, get_digest_contents
from pants.util.frozendict import FrozenDict

try:
    import toml
except ModuleNotFoundError:
    import tomllib as toml

from pants.base.specs import Specs
from pants.engine.collection import Collection
from pants.engine.internals.selectors import concurrently
from pants.engine.internals.specs_rules import resolve_specs_paths
from pants.engine.rules import collect_rules, implicitly, rule
from pants.source.source_root import SourceRootRequest, get_source_root
from pants.util.ordered_set import OrderedSet


PythonConfigValue = Union[bool, int, float, str, tuple["PythonConfigValue"], FrozenDict[str, "PythonConfigValue"]]
PythonConfigSection = FrozenDict[str, FrozenDict[str, PythonConfigValue]]


@dataclass(frozen=True)
class PythonConfig:
    path: Path
    _values: FrozenDict

    @classmethod
    def from_pyproject_toml(cls, path: Path, content: str) -> "PythonConfig":
        return cls(path=path, _values=FrozenDict.deep_freeze(toml.loads(content)))

    def get_section(self, section_name: str) -> Optional[PythonConfigSection]:
        mapping = self._values
        section_name_parts = section_name.split(".")
        for section_name_part in section_name_parts:
            mapping = mapping.get(section_name_part)
            if not mapping:
                return mapping
        return mapping

    def get_section_or_error(self, section_name: str) -> PythonConfigSection:
        section = self.get_section(section_name)
        if isinstance(section, FrozenDict):
            return section
        if section is None:
            err = f"No section [{section_name}] found in {self.path}"
        else:
            err = f"Value for section [{section_name}] in {self.path} is not a table."
        raise ValueError(err)

    def get(self, section_name: str, key: str, default: Optional[PythonConfigValue]=None) -> Optional[PythonConfigValue]:
        section = self.get_section(section_name)
        if not isinstance(section, FrozenDict):
            return default
        return section.get(key, default)

    def get_or_error(self, section_name: str, key: str) -> PythonConfigValue:
        section = self.get_section_or_error(section_name)
        val = section.get(key)
        if val is None:
            raise ValueError(f"No value for `{key}` found in section [{section_name}] in {self.path}")
        return val


@dataclass(frozen=True)
class OptionalPythonConfig:
    config: Optional[PythonConfig]


_repo_root = Path("")


@rule
async def get_python_config_for_directory(directory: Path) -> OptionalPythonConfig:
    path = directory / "pyproject.toml"
    digest = await path_globs_to_digest(PathGlobs([str(path)]))
    digest_contents = await get_digest_contents(digest)
    if not len(digest_contents):
        if directory == _repo_root:
            return OptionalPythonConfig(config=None)
        return await get_python_config_for_directory(directory.parent)
    file_contents = next(iter(digest_contents))
    return OptionalPythonConfig(
        config=PythonConfig.from_pyproject_toml(path, file_contents.content.decode()))


@dataclass(frozen=True)
class PythonPartition:
    source_root: Path
    settings: PythonSettings.EnvironmentAware
    config: Optional[PythonConfig]
    source_files: Tuple[Path, ...]

    def config_or_error(self) -> PythonConfig:
        if self.config is None:
            raise (f"No pyproject.toml or equivalent config file found "
                   f"for source root {self.source_root}")
        return self.config


class PythonPartitions(Collection[PythonPartition]):
    pass


@rule
async def compute_partitions(specs: Specs, settings: PythonSettings.EnvironmentAware) -> PythonPartitions:
    """Partition in the input specs.

    We run separate processes for each partition (and may subpartition further
    for performance reasons). A few things determine partitioning:

    - Distinct source roots.
    - Distinct config.
    - ... ?
    """
    specs_paths = await resolve_specs_paths(specs, **implicitly())
    files = OrderedSet(Path(f) for f in specs_paths.files)  # Note that these are all files, not dirs.
    # All files in the same dir belong to the same source root, so we only need to look up parents.
    dir_to_files = defaultdict(list)
    for file in files:
        dir_to_files[file.parent].append(file)
    dirs = list(dir_to_files.keys())

    source_roots = await concurrently(
        get_source_root(SourceRootRequest(d), **implicitly())
        for d in dirs

    )
    source_root_to_files = defaultdict(list)
    for (d, sr) in zip(dirs, source_roots):
        source_root_to_files[sr].extend(dir_to_files[d])

    # Note that the same source root may appear multiple times in source_roots.
    # To get distinct source roots, we iterate over the keys of source_root_to_files.
    opt_configs = await concurrently(
        get_python_config_for_directory(Path(source_root.path))
        for source_root in source_root_to_files.keys()
    )

    return PythonPartitions(
        PythonPartition(source_root=sr, settings=settings, config=opt_config.config, source_files=tuple(Path(f) for f in files))
        # Note that we rely on consistent dict iteration order.
        for sr, files, opt_config in zip(source_root_to_files.keys(), source_root_to_files.values(), opt_configs)
    )

def rules():
    return collect_rules()
