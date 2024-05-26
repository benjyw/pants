# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).
from pants.backend.python_new.uv import download_uv
from pants.engine.console import Console
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
    foo_subsystem: FooSubsystem,
) -> Foo:
    uv = await download_uv(**implicitly())
    with foo_subsystem.line_oriented(console) as print_stdout:
        print_stdout(uv.exe)
    return Foo(exit_code=0)


def rules():
    return collect_rules()
