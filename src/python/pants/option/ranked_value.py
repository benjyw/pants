# Copyright 2014 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import total_ordering
from typing import Any, Iterator, Optional, Tuple, Union

from pants.util.frozendict import FrozenDict


# NB: Must mirror the Rank enum in src/rust/engine/options/src/lib.rs.
@total_ordering
class Rank(Enum):
    # The ranked value sources. Higher ranks override lower ones.
    NONE = (0, "NONE")  # The value None.
    HARDCODED = (1, "HARDCODED")  # The default provided at option registration.
    CONFIG_DEFAULT = (2, "CONFIG_DEFAULT")  # The value from the DEFAULT section of the config file.
    CONFIG = (3, "CONFIG")  # The value from the relevant section of the config file.
    ENVIRONMENT = (4, "ENVIRONMENT")  # The value from the appropriately-named environment variable.
    FLAG = (5, "FLAG")  # The value from the appropriately-named command-line flag.

    _rank: int

    def __new__(cls, rank: int, display: str) -> Rank:
        member: Rank = object.__new__(cls)
        member._value_ = display
        member._rank = rank
        return member

    def __lt__(self, other: Any) -> bool:
        if type(other) != Rank:  # noqa: E721
            return NotImplemented
        return self._rank < other._rank

    def description(self) -> Optional[str]:
        """The source descriptions used to display option value derivation to users."""
        # These specific strings are for compatibility with the legacy parser's tests.
        # We may revisit them once that is gone.
        if self == Rank.CONFIG:
            return "from config"
        if self == Rank.ENVIRONMENT:
            return "from an env var"
        if self == Rank.FLAG:
            return "from command-line flag"
        return None


Value = Union[None, str, int, float, FrozenDict, Enum, Tuple]
ValueAndDetails = Tuple[Optional[Value], Optional[str]]


def hashable(obj: Any) -> Value:
    if isinstance(obj, (type(None), str, int, float, Enum)):
        return obj
    if isinstance(obj, (list, tuple)):
        return tuple(hashable(x) for x in obj)
    if isinstance(obj, (dict, FrozenDict)):
        return FrozenDict((k, hashable(v)) for k, v in obj.items())
    raise ValueError(f"Unsupported option value type: {type(obj)}")


@dataclass(frozen=True)
class RankedValue:
    """An option value, together with a rank inferred from its source.

     Allows us to control which source wins: e.g., a command-line flag overrides an environment
     variable which overrides a config, etc. For example:

     Consider this config:

     [compile.java]
     foo: 11

     And this environment variable:

     PANTS_COMPILE_FOO: 22

    If the command-line is

     ./pants compile target

     we expect the value of foo in the compile.java scope to be 22, because it was explicitly
     set by the user in the enclosing compile scope. I.e., the outer scope's environment value
     overrides the inner scope's config value.

     However if the command-line is

     ./pants compile.java --foo=33 target

     we now expect the value of foo in the compile.java to be 33. I.e., the inner scope's flag
     overrides the outer scope's environment value.

     To tell these cases apart we need to know the "ranking" of the value.
    """

    def __init__(self, rank: Rank, value: Any, details: str | None = None):
        object.__setattr__(self, "rank", rank)
        object.__setattr__(self, "value", hashable(value))
        object.__setattr__(self, "details", details)

    @classmethod
    def prioritized_iter(
        cls,
        flag_val: ValueAndDetails,
        env_val: ValueAndDetails,
        config_val: ValueAndDetails,
        config_default_val: ValueAndDetails,
        hardcoded_val: ValueAndDetails,
        default: ValueAndDetails,
    ) -> Iterator[RankedValue]:
        """Yield the non-None values from highest-ranked to lowest, as RankedValue instances."""
        if flag_val[0] is not None:
            yield RankedValue(Rank.FLAG, *flag_val)
        if env_val[0] is not None:
            yield RankedValue(Rank.ENVIRONMENT, *env_val)
        if config_val[0] is not None:
            yield RankedValue(Rank.CONFIG, *config_val)
        if config_default_val[0] is not None:
            yield RankedValue(Rank.CONFIG_DEFAULT, *config_default_val)
        if hardcoded_val[0] is not None:
            yield RankedValue(Rank.HARDCODED, *hardcoded_val)
        yield RankedValue(Rank.NONE, *default)

    rank: Rank
    value: Value
    details: str | None  # Optional details about the derivation of the value.
