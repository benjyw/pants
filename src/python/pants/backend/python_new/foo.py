# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Mapping

from pants.backend.python_new.uv import download_uv
from pants.base.specs import Specs
from pants.engine.console import Console
from pants.engine.fs import Paths
from pants.engine.goal import Goal, GoalSubsystem, LineOriented
from pants.engine.internals.specs_rules import resolve_specs_paths
from pants.engine.rules import collect_rules, goal_rule, implicitly, rule


class FooSubsystem(LineOriented, GoalSubsystem):
    name = "foo"
    help = "For mucking around."


class Foo(Goal):
    subsystem_cls = FooSubsystem
    environment_behavior = Goal.EnvironmentBehavior.LOCAL_ONLY


@dataclass(frozen=True)
class PythonProject:
    project_root: Path  # Directory containing pyproject.toml or similar, relative to build root.
    sources: tuple[Path, ...]  # Source files relative to project_root.


@dataclass(frozen=True)
class PythonPartition:
    files: Tuple[Path, ...]


@rule
async def compute_partitions(specs: Specs) -> PythonPartition:
    specs_paths = await resolve_specs_paths(specs, **implicitly())
    files = {Path(f) for f in specs_paths.files}  # Note that these are actual files, not dirs.
    pyproject_files = tuple(sorted(file for file in files if file.name == "pyproject.toml"))
    for pyproject_file in pyproject_files:
        project_root = pyproject_file.parent
        project_files = []
        for file in files:
            try:
                rel_file = file.relative_to(project_root)
            except ValueError:
                pass  # Thrown if file is not relative to project_root


    return PythonPartition(files=tuple(Path(f) for f in specs_paths.files))


@goal_rule
async def foo(
    console: Console,
    foo_subsystem: FooSubsystem,
) -> Foo:
    partitions = await compute_partitions(**implicitly())
    uv = await download_uv(**implicitly())
    with foo_subsystem.line_oriented(console) as print_stdout:
        print_stdout(uv.exe)
        print_stdout(partitions)
    return Foo(exit_code=0)


def rules():
    return collect_rules()
