# Copyright 2025 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.backend.build_files.utils import collect_rules
from pants.backend_ng.python.code_quality import CodeQualityResult, CodeQualityResults
from pants.backend_ng.python.requirements import get_requirements
from pants.backend_ng.python.ruff import Ruff
from pants.backend_ng.python.uv import UvCommand, execute_uv_command
from pants.base.specs import Specs
from pants.engine.console import Console
from pants.engine.fs import Workspace
from pants.engine.internals.native_engine import MergeDigests
from pants.engine.intrinsics import merge_digests
from pants.engine.rules import concurrently, goal_rule, implicitly, rule
from pants.ng.source_partition import SourcePartition, SourcePaths, partition_sources
from pants.ng.goal import GoalNg, GoalSubsystemNg
from pants.util.logging import LogLevel


class FormatSubsystem(GoalSubsystemNg):
    options_scope = "format"
    help = "Run formatters."


class Format(GoalNg):
    subsystem_cls = FormatSubsystem


@rule(desc="Format", level=LogLevel.INFO)
async def format_partition(source_paths: SourcePaths, format_subsystem: FormatSubsystem, ruff: Ruff) -> CodeQualityResult:
    # TODO: Support other linters. Right now we only support ruff. It should be much simpler than
    #  with og pants, since `uv tool run` can set them up and run them for us.
    ruff_reqs = await get_requirements(ruff.requirements_request())
    uv_args = ("tool", "run", *(f"--with={req}" for req in ruff_reqs.requirement_strings), "ruff", "check")
    uv_command = UvCommand(f"Run `ruff format`", uv_args, source_paths)
    uv_result = await execute_uv_command(uv_command)
    # Ruff exits with 0 or 1 in normal operation. `uv run tool` passes the underlying tool's
    # exit codes through. Unfortunately uv may also exit 1 to signal errors in setting
    # up the tool, such as a bad requirement. In such cases we will mistakenly interpret this
    # as a normal ruff error and display it as such.
    # See https://docs.astral.sh/ruff/linter/#exit-codes.
    if uv_result.exit_code not in {0, 1}:
        raise Exception(f"`uv tool run ruff` exited with code {uv_result.exit_code} due to: {uv_result.stderr}")
    return CodeQualityResult(uv_result)


@rule
async def do_format(specs: Specs) -> CodeQualityResults:
    partitions = await partition_sources(specs.includes.to_specs_paths_path_globs(), **implicitly())
    partition_results = await concurrently(format_partition(**implicitly({partition: SourcePartition})) for partition in partitions)
    return CodeQualityResults(partition_results)


@goal_rule
async def format(
    console: Console,
    workspace: Workspace,
    specs: Specs,
) -> Format:
    results = await do_format(specs, **implicitly())
    output = await merge_digests(MergeDigests(result.uv_result.output_digest for result in results))
    workspace.write_digest(output)
    lockfiles = await merge_digests(MergeDigests(result.uv_result.lockfile_digest for result in results))
    workspace.write_digest(lockfiles)
    return Format(results.exit_code())


def rules():
    return [*collect_rules()]
