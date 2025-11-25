# Copyright 2025 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.backend_ng.python import dependencies, format, interpreter, lint, lockfile, project, python_tool, requirements, ruff, test, uv


def rules():
    return (
        *dependencies.rules(),
        *format.rules(),
        *interpreter.rules(),
        *lint.rules(),
        *lockfile.rules(),
        *project.rules(),
        *python_tool.rules(),
        *requirements.rules(),
        *ruff.rules(),
        *test.rules(),
        *uv.rules(),
    )