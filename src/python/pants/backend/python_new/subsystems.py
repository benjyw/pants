# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.option.option_types import DictOption, StrOption
from pants.option.subsystem import Subsystem
from pants.util.strutil import softwrap


class PythonSettings(Subsystem):
    options_scope = "python-new"
    help = "Python-related settings for the repo."

    settings_dir = StrOption(
        default = "python-settings",
        help = softwrap(
            """
            Python-related settings files are generated under this directory.
            
            These files are intended to be checked in to the repo.
            """
        )
    )

    interpreters = DictOption[str](
        default=None,
        help=softwrap(
            """
            The Python interpreters in use in your repo.

            Must be a map from logical name, such as 'py3.11' to fully-specified
            Python version, such as 'CPython==3.11.6' or 'PyPy==pypy3.10-7.3.12'. 
            Wildcards are not allowed.
            """
        ),
        metavar="<interpreter mapping>",
    )

    default_interpreter = StrOption(
        default=None,
        help="One of the interpreter names as specified by the `interpreters` option in this scope."
    )
