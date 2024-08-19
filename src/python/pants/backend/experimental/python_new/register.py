# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

"""New implementation of support for Python."""

from pants.backend.python_new import register


def rules():
    return register.rules()


def target_types():
    return register.target_types()
