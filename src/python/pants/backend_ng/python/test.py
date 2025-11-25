# Copyright 2026 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from dataclasses import dataclass
from pants.backend.build_files.utils import collect_rules
from pants.backend_ng.python.dependencies import find_transitive_deps
from pants.backend_ng.python.python_tool import ProjectTool
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
from pants.ng.source_partition import SourcePartition, SourcePaths, partition_sources
from pants.ng.goal import GoalNg, GoalSubsystemNg
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
            if (ec := result.exit_code()):
                return ec
        return 0


class Pytest(ProjectTool):
    options_scope = "pytest"


@rule(desc="Test", level=LogLevel.INFO)
async def test_partition(source_paths: SourcePaths, test_subsystem: TestSubsystem) -> TestResult:
    transitive_closure = await find_transitive_deps(source_paths)
    digest = await path_globs_to_digest(
        PathGlobs(
            globs=tuple(str(object=path) for path in transitive_closure.paths),
            glob_match_error_behavior=GlobMatchErrorBehavior.ignore,
            conjunction=GlobExpansionConjunction.all_match,
        )
    )

    uv_args = ["run", "pytest"]
    uv_command = UvCommand(f"Run pytest", uv_args=tuple(uv_args), source_paths=source_paths, extra_input_digest=digest)
    uv_result: UvProcessResult = await execute_uv_command(uv_command)
    return TestResult(uv_result)


@rule
async def do_test(specs: Specs) -> TestResults:
    partitions = await partition_sources(specs.includes.to_specs_paths_path_globs(), **implicitly())
    partition_results = await concurrently(test_partition(**implicitly({partition: SourcePartition})) for partition in partitions)
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
    lockfiles = await merge_digests(MergeDigests(result.uv_result.lockfile_digest for result in results))
    workspace.write_digest(lockfiles)
    return Test(results.exit_code())


def rules():
    return [*collect_rules()]
