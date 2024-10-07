# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.backend.python_new.interpreter import generate_complete_platform, InterpreterConstraint, \
    get_complete_platform_path
from pants.backend.python_new.lockfile import generate_lockfile_for_partition
from pants.backend.python_new.partition import compute_partitions, PythonPartition
from pants.backend.python_new.subsystems import PythonSettings
from pants.engine.console import Console
from pants.engine.fs import Workspace
from pants.engine.goal import Goal, GoalSubsystem, LineOriented
from pants.engine.internals.native_engine import MergeDigests
from pants.engine.internals.selectors import concurrently
from pants.engine.intrinsics import merge_digests, get_digest_entries
from pants.engine.rules import collect_rules, goal_rule, implicitly

import logging

from pants.option.option_types import BoolOption

logger = logging.getLogger(__name__)


class InterpreterSubsystem(LineOriented, GoalSubsystem):
    name = "interpreter"
    help = "Manage configured interpreters."

    inspect = BoolOption(
        default=False,
        help="Inspect the configured interpreters, generating complete platforms data."
    )


class InterpreterGoal(Goal):
    subsystem_cls = InterpreterSubsystem
    environment_behavior = Goal.EnvironmentBehavior.LOCAL_ONLY


@goal_rule
async def interpreter(
    console: Console,
    workspace: Workspace,
    interpreter_subsystem: InterpreterSubsystem,
    python_settings: PythonSettings,
) -> InterpreterGoal:
    if interpreter_subsystem.inspect:
        complete_platforms = await concurrently(
            generate_complete_platform(
                get_complete_platform_path(name, python_settings),
                InterpreterConstraint(constraint_str)) for name, constraint_str in python_settings.interpreters.items()
        )
        merged_digest = await merge_digests(MergeDigests(complete_platform.digest for complete_platform in complete_platforms))
        workspace.write_digest(merged_digest)
        digest_entries = await get_digest_entries(merged_digest)
        with interpreter_subsystem.line_oriented(console) as print_stdout:
            for digest_entry in digest_entries:
                print_stdout(f"Wrote complete platform to {digest_entry.path}")
        return InterpreterGoal(exit_code=0)
    else:
        raise Exception("Must provide one of the following switches: --inspect")


class LockSubsystem(LineOriented, GoalSubsystem):
    name = "lock"
    help = "Manage dependency lockfiles."

    generate = BoolOption(
        default=False,
        help="Generate the specified lockfiles."
    )


class LockGoal(Goal):
    subsystem_cls = LockSubsystem
    environment_behavior = Goal.EnvironmentBehavior.LOCAL_ONLY


@goal_rule
async def lock(
        console: Console,
        workspace: Workspace,
        lock_subsystem: LockSubsystem,
        python_settings: PythonSettings,
) -> LockGoal:
    if lock_subsystem.generate:
        partitions = await compute_partitions(**implicitly())
        lockfiles = await concurrently(
            generate_lockfile_for_partition(**implicitly({partition: PythonPartition}))
            for partition in partitions
        )

        merged_digest = await merge_digests(
            MergeDigests(lockfile.digest for lockfile in lockfiles)
        )
        workspace.write_digest(merged_digest)
        digest_entries = await get_digest_entries(merged_digest)
        with lock_subsystem.line_oriented(console) as print_stdout:
            for digest_entry in digest_entries:
                print_stdout(f"Wrote lockfile to {digest_entry.path}")
        return LockGoal(exit_code=0)
    else:
        raise Exception("Must provide one of the following switches: --generate")


def rules():
    return collect_rules()
