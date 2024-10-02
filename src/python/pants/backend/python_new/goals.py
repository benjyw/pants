# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.backend.python_new.interpreter import generate_complete_platform, InterpreterConstraint

from pants.engine.fs import Workspace

from pants.engine.console import Console
from pants.engine.goal import Goal, GoalSubsystem, LineOriented
from pants.engine.rules import collect_rules, goal_rule


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
) -> InspectInterpreters:
    complete_platform = await generate_complete_platform(InterpreterConstraint("==3.11.9"))
    workspace.write_digest(complete_platform.digest)
    return InspectInterpreters(exit_code=0)


def rules():
    return collect_rules()
