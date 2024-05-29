# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Mapping

from pants.backend.python_new.uv import download_uv
from pants.base.specs import Specs
from pants.engine.collection import Collection
from pants.engine.console import Console
from pants.engine.fs import Paths
from pants.engine.goal import Goal, GoalSubsystem, LineOriented
from pants.engine.internals.selectors import MultiGet, concurrently
from pants.engine.internals.specs_rules import resolve_specs_paths
from pants.engine.rules import collect_rules, goal_rule, implicitly, rule
from pants.source.source_root import get_optional_source_root, SourceRootRequest
from pants.util.ordered_set import OrderedSet


class FooSubsystem(LineOriented, GoalSubsystem):
    name = "foo"
    help = "For mucking around."


class Foo(Goal):
    subsystem_cls = FooSubsystem
    environment_behavior = Goal.EnvironmentBehavior.LOCAL_ONLY


@dataclass(frozen=True)
class PythonPartition:
    source_root: Path
    files: Tuple[Path, ...]


class PythonPartitions(Collection[PythonPartition]):
    pass


@rule
async def compute_partitions(specs: Specs) -> PythonPartition:
    """Partition in the input specs.

    We run separate processes for each partition (and may subpartition further
    for performance reasons). A few things determine partitioning:

    - Distinct source roots.
    - Distinct config.
    - ... ?
    """
    specs_paths = await resolve_specs_paths(specs, **implicitly())
    files = OrderedSet(Path(f) for f in specs_paths.files)  # Note that these are actual files, not dirs.
    # All files in the same dir belong to the same source root, so we only need to look up parents.
    dir_to_files = defaultdict(list)
    for file in files:
        dir_to_files[file.parent].append(file)
    dirs = list(dir_to_files.keys())

    source_roots = await concurrently(
        [get_optional_source_root(SourceRootRequest(Path("zzz")), **implicitly()),
         get_optional_source_root(SourceRootRequest(Path("yyy")), **implicitly())]
    )

    source_root_to_files = defaultdict(list)
    for (d, sr) in zip(dirs, source_roots):
        source_root_to_files[sr].extend(dir_to_files[d])


    return PythonPartitions(
        PythonPartition(source_root=sr, files=tuple(Path(f) for f in files))
        for sr, files in sorted(source_root_to_files.items())
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
