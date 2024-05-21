# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

"""New implementation of support for Python."""

from pants.backend.experimental.python_new import uv

def rules():
    return (
        *uv.rules(),
    )


def target_types():
    return tuple()
