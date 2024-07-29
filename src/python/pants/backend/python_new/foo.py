# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PosixPath
from typing import Tuple, Optional

from pants.engine.fs import PathGlobs
from pants.engine.intrinsics import path_globs_to_digest, directory_digest_to_digest_contents

try:
    import toml
except ModuleNotFoundError:
    import tomllib as toml

from pants.backend.python_new.uv import download_uv
from pants.base.specs import Specs
from pants.engine.collection import Collection
from pants.engine.console import Console
from pants.engine.goal import Goal, GoalSubsystem, LineOriented
from pants.engine.internals.selectors import concurrently, Get
from pants.engine.internals.specs_rules import resolve_specs_paths
from pants.engine.rules import collect_rules, goal_rule, implicitly, rule
from pants.source.source_root import SourceRootRequest, get_source_root
from pants.util.ordered_set import OrderedSet


class FooSubsystem(LineOriented, GoalSubsystem):
    name = "foo"
    help = "For mucking around."


class Foo(Goal):
    subsystem_cls = FooSubsystem
    environment_behavior = Goal.EnvironmentBehavior.LOCAL_ONLY


@dataclass(frozen=True)
class PythonConfig:
    values: Optional[dict]

    @classmethod
    def from_pyproject_toml_contents(cls, pyproject_toml_contents: str) -> "PythonConfig":
        return cls(values=toml.loads(pyproject_toml_contents))

_repo_root = Path("")


@rule
async def get_python_config(directory: PosixPath) -> PythonConfig:
    if directory == _repo_root:
        return PythonConfig(values=None)
    digest = await path_globs_to_digest(PathGlobs([str(directory / "pyproject.toml")]))
    digest_contents = await directory_digest_to_digest_contents(digest)
    if not len(digest_contents):
        return await get_python_config(directory.parent)
    file_contents = next(iter(digest_contents))
    return PythonConfig.from_pyproject_toml_contents(file_contents.content.decode())


@dataclass(frozen=True)
class PythonPartition:
    source_root: Path
    config: PythonConfig
    source_files: Tuple[Path, ...]


class PythonPartitions(Collection[PythonPartition]):
    pass


@rule
async def compute_partitions(specs: Specs) -> PythonPartitions:
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
    configs = await concurrently(
        get_python_config(Path(source_root.path))
        for source_root in source_root_to_files.keys()
    )

    return PythonPartitions(
        PythonPartition(source_root=sr, config=config, source_files=tuple(Path(f) for f in files))
        # Note that we rely on consistent dict iteration order.
        for sr, files, config in zip(source_root_to_files.keys(), source_root_to_files.values(), configs)
    )


@goal_rule
async def foo(
    console: Console,
    foo_subsystem: FooSubsystem,
) -> Foo:
    partitions = await compute_partitions(**implicitly())
    uv = await download_uv(**implicitly())
    with foo_subsystem.line_oriented(console) as print_stdout:
        print_stdout(partitions)
    return Foo(exit_code=0)


def rules():
    return collect_rules()
