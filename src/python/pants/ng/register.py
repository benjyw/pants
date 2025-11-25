# Copyright 2025 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).


from pants.engine.rules import Rule
from pants.ng import source_partition, subsystem


def rules() -> tuple[Rule, ...]:
    return (
        *source_partition.rules(),
        *subsystem.rules(),
    )
