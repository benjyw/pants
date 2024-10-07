# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.backend.python.util_rules.pex_cli import download_pex_pex
from pants.backend.python_new.partition import compute_partitions
from pants.backend.python_new.uv import download_uv
from pants.engine.console import Console
from pants.engine.fs import Workspace
from pants.engine.goal import Goal, GoalSubsystem, LineOriented
from pants.engine.rules import collect_rules, goal_rule, implicitly


class FooSubsystem(LineOriented, GoalSubsystem):
    name = "foo"
    help = "For mucking around."


class Foo(Goal):
    subsystem_cls = FooSubsystem
    environment_behavior = Goal.EnvironmentBehavior.LOCAL_ONLY


@goal_rule
async def foo(
    console: Console,
    workspace: Workspace,
    foo_subsystem: FooSubsystem,
) -> Foo:
    partitions = await compute_partitions(**implicitly())
    uv = await download_uv(**implicitly())
    pex = await download_pex_pex(**implicitly())
    return Foo(exit_code=0)


def rules():
    return collect_rules()
