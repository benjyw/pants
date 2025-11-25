# Copyright 2026 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.backend_ng.python.python_tool import IsolatedTool
from pants.engine.rules import collect_rules


class Ruff(IsolatedTool):
    options_scope = "ruff"


def rules():
    return [*collect_rules()]
