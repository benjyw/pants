# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

"""New implementation of support for Python."""

from pants.backend.python.util_rules import pex
from pants.backend.python_new import foo, uv, lockfile


def rules():
    return (
        *uv.rules(),
        *foo.rules(),
        *lockfile.rules(),
        *pex.rules(),
    )


def target_types():
    return tuple()
