# Copyright 2026 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from dataclasses import dataclass
from pathlib import Path

from pants.backend.build_files.utils import collect_rules
from pants.backend_ng.python.dependencies import find_transitive_deps
from pants.backend_ng.python.uv import UvCommand, UvProcessResult, execute_uv_command
from pants.base.glob_match_error_behavior import GlobMatchErrorBehavior
from pants.base.specs import Specs
from pants.engine.collection import Collection
from pants.engine.console import Console
from pants.engine.engine_aware import EngineAwareReturnType
from pants.engine.fs import GlobExpansionConjunction, PathGlobs, Workspace
from pants.engine.internals.native_engine import MergeDigests
from pants.engine.intrinsics import merge_digests, path_globs_to_digest
from pants.engine.rules import concurrently, goal_rule, implicitly, rule
from pants.ng.goal import GoalNg, GoalSubsystemNg
from pants.ng.passthru import PassthruArgs
from pants.ng.source_partition import SourcePartition, SourcePaths, partition_sources
from pants.util.logging import LogLevel


class TestSubsystem(GoalSubsystemNg):
    options_scope = "test"
    help = "Run tests."


class Test(GoalNg):
    subsystem_cls = TestSubsystem


@dataclass(frozen=True)
class TestResult(EngineAwareReturnType):
    uv_result: UvProcessResult

    def exit_code(self) -> int:
        return self.uv_result.exit_code

    def message(self) -> str | None:
        return self.uv_result.message()

    def level(self) -> LogLevel | None:
        if self.exit_code() != 0:
            return LogLevel.ERROR
        return LogLevel.INFO

    def cacheable(self) -> bool:
        return True


class TestResults(Collection[TestResult]):
    def exit_code(self) -> int:
        for result in reversed(self):
            if ec := result.exit_code():
                return ec
        return 0


# class Pytest(ProjectTool):
#     options_scope = "pytest"


@dataclass(frozen=True)
class TestFiles:
    paths: tuple[str, ...]


@rule(desc="Test", level=LogLevel.INFO)
async def test_partition(
    source_paths: SourcePaths, test_subsystem: TestSubsystem, passthru: PassthruArgs
) -> TestResult:
    py_source_paths = source_paths.filter_by_suffixes((".py", ".pyi"))
    transitive_closure = await find_transitive_deps(source_paths, **implicitly())
    digest = await path_globs_to_digest(
        PathGlobs(
            globs=tuple(str(object=path) for path in transitive_closure.paths),
            glob_match_error_behavior=GlobMatchErrorBehavior.ignore,
            conjunction=GlobExpansionConjunction.all_match,
        )
    )
    passthru_args = passthru.args or tuple()

    # Collect test files.
    uv_args = [
        "run",
        "pytest",
        "--collect-only",
        "-qq",
        *passthru_args,
        *py_source_paths.path_strs(),
    ]
    uv_command = UvCommand(
        f"Collect test files",
        uv_args=tuple(uv_args),
        source_paths=py_source_paths,
        input_digest=digest,
        must_succeed=True,
    )
    uv_result: UvProcessResult = await execute_uv_command(uv_command)
    # The output of `pytest --collect-only -qq` is lines of the form "path/to/test.py: <num tests>".
    discovered_test_files = [
        path.rsplit(":", 1)[0] for path in uv_result.stdout.splitlines() if path
    ]

    # Run tests. We pass the files in explicitly to avoid the cost of test collection again.
    uv_args = ["run", "pytest", *passthru_args, *discovered_test_files]
    test_files = SourcePaths(
        tuple(Path(path) for path in discovered_test_files), py_source_paths.source_root
    )
    uv_command = UvCommand(
        f"Run pytest", uv_args=tuple(uv_args), source_paths=test_files, input_digest=digest
    )
    uv_result: UvProcessResult = await execute_uv_command(uv_command)
    return TestResult(uv_result)


@rule
async def do_test(specs: Specs) -> TestResults:
    partitions = await partition_sources(specs.includes.to_specs_paths_path_globs(), **implicitly())
    partition_results = await concurrently(
        test_partition(**implicitly({partition: SourcePartition})) for partition in partitions
    )
    return TestResults(partition_results)


@goal_rule
async def test(
    console: Console,
    workspace: Workspace,
    specs: Specs,
) -> Test:
    results = await do_test(specs, **implicitly())
    output = await merge_digests(MergeDigests(result.uv_result.output_digest for result in results))
    workspace.write_digest(output)
    lockfiles = await merge_digests(
        MergeDigests(result.uv_result.lockfile_digest for result in results)
    )
    workspace.write_digest(lockfiles)
    return Test(results.exit_code())


def rules():
    return [*collect_rules()]
