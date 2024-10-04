# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.backend.python_new.interpreter import generate_complete_platform, InterpreterConstraint, \
    get_complete_platform_path
from pants.backend.python_new.subsystems import PythonSettings
from pants.engine.console import Console
from pants.engine.fs import Workspace
from pants.engine.goal import Goal, GoalSubsystem, LineOriented
from pants.engine.internals.native_engine import MergeDigests
from pants.engine.internals.selectors import concurrently
from pants.engine.intrinsics import merge_digests, get_digest_contents, get_digest_entries
from pants.engine.rules import collect_rules, goal_rule

import logging

logger = logging.getLogger(__name__)


class InspectInterpretersSubsystem(LineOriented, GoalSubsystem):
    name = "inspect-interpreters"
    help = "Inspect configured interpreters."


class InspectInterpreters(Goal):
    subsystem_cls = InspectInterpretersSubsystem
    environment_behavior = Goal.EnvironmentBehavior.LOCAL_ONLY


@goal_rule
async def inspect_interpreters(
    console: Console,
    workspace: Workspace,
    inspect_interpreters_subsystem: InspectInterpretersSubsystem,
    python_settings: PythonSettings,
) -> InspectInterpreters:
    complete_platforms = await concurrently(
        generate_complete_platform(
            get_complete_platform_path(name, python_settings),
            InterpreterConstraint(constraint_str)) for name, constraint_str in python_settings.interpreters.items()
    )
    merged_digest = await merge_digests(MergeDigests(complete_platform.digest for complete_platform in complete_platforms))
    workspace.write_digest(merged_digest)
    digest_entries = await get_digest_entries(merged_digest)
    for digest_entry in digest_entries:
        logger.info(f"Wrote {digest_entry.path}")
    return InspectInterpreters(exit_code=0)


def rules():
    return collect_rules()
