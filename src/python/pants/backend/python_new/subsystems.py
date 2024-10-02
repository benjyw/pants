# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.option.option_types import DictOption
from pants.option.subsystem import Subsystem
from pants.util.strutil import softwrap


class PythonConfig(Subsystem):
    interpreters = DictOption[str](
        default=None,
        help=softwrap(
            """
            The Python interpreters in use in your codebase.

            Must be a list of fully-specified Python versions, such as
            'CPython==3.11.6' or 'PyPy==pypy3.10-7.3.12'. Wildcards are not allowed.
            """
        ),
        metavar="<interpreter version>",
    )