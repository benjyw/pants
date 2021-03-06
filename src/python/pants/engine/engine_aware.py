# Copyright 2020 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from abc import ABC
from typing import Dict, Optional

from pants.engine.fs import Snapshot
from pants.util.logging import LogLevel


class EngineAwareParameter(ABC):
    """A marker class for rule parameters that allows sending additional metadata to the engine.

    When Pants executes a rule, the engine will call this marker class's methods on the rule's
    inputs to see if they implement any of the methods. If the method returns `None`, the engine
    will do nothing; otherwise, it will use the additional metadata provided.
    """

    def debug_hint(self) -> Optional[str]:
        """If implemented, this string will be shown in `@rule` debug contexts if that rule takes
        the annotated type as a parameter."""
        return None


class EngineAwareReturnType(ABC):
    """A marker class for types that are returned by rules to allow sending additional metadata to
    the engine.

    When Pants finishes executing a rule, the engine will call this marker class's methods to see if
    it implements any of the methods. If the method returns `None`, the engine will do nothing;
    otherwise, it will use the additional metadata provided.
    """

    def level(self) -> Optional[LogLevel]:
        """If implemented, this method will modify the level of the workunit associated with any
        `@rule`s that return the annotated type.

        For instance, this can be used to change a workunit that would normally be at `Debug` level
        to `Warn` if an anomalous condition occurs within the `@rule`.
        """
        return None

    def message(self) -> Optional[str]:
        """If implemented, this adds a result message to the workunit for any `@rule`'s that return
        the annotated type.

        The final message will take the form "Completed: <Rule description> - <this method's return
        value>". This method may use newlines.
        """
        return None

    def artifacts(self) -> Optional[Dict[str, Snapshot]]:
        """If implemented, this sets the `artifacts` entry for the workunit of any `@rule`'s that
        return the annotated type.

        `artifacts` is a mapping of arbitrary string keys to `Snapshot`s.
        """
        return None
