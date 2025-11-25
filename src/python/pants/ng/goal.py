# Copyright 2025 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from dataclasses import dataclass
from typing import Iterable, cast

from pants.engine.goal import Goal
from pants.engine.rules import Rule
from pants.ng.subsystem import UniversalSubsystem
from pants.util.meta import classproperty


@dataclass(frozen=True)
class GoalNg(Goal):
    """A Goal registered by Pants NG.

    NG can use all existing rules except goal_rules, since its UI is different. It can register its
    own goal rules, and therefore have different goal-associated subsystems using the same names.
    """

    # Pants NG doesn't use the environments feature yet (and may never need to).
    environment_behavior = Goal.EnvironmentBehavior.LOCAL_ONLY


class GoalSubsystemNg(UniversalSubsystem):
    """A Pants NG goal's subsystem."""

    @classproperty
    def name(cls) -> str:
        return cast(str, cls.options_scope)

    @classmethod
    def rules(cls) -> Iterable[Rule]:
        """An NG subsystem doesn't yield any rules to create instances of itself."""
        return []
