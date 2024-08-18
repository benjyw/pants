# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).
from dataclasses import dataclass
from typing import Tuple

from pants.engine.internals.native_engine import Digest
from pants.engine.rules import rule


@dataclass(frozen=True)
class Lockfile:
    digest: Digest


@rule
async def generate_lockfile(requirements: Tuple[str, ...]) -> Lockfile:
    pass