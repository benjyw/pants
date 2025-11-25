# Copyright 2025 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).


from pants.engine.rules import collect_rules
from pants.ng.subsystem import ContextualSubsystem, option
from pants.util.strutil import softwrap


class PythonProject(ContextualSubsystem):
    options_scope = "pyproject"
    help = "Options for setting up a Python project."

    @option(default="pyproject.toml", help="Path to project file")
    def project(self) -> str: ...

    interpreter_version_help = softwrap(
        """
        The constaints on the interpreter to use, e.g., `==3.12.7`.

        The feature of reading option values from other files is useful here:
        A value of @path/to/pyproject.toml:project.required-python will take the relevant value
        from the pyproject.toml file.
        """
    )

    @option(required=True, help="The constaints on the interpreter to use, e.g., `==3.12.7`.")
    def interpreter_version(self) -> str: ...

    requirements_help = softwrap(
        """
        3rd-party requirements strings.

        The feature of reading option values from other files is useful here:
        A value of @path/to/pyproject.toml:project.dependencies will take the relevant values
        from the pyproject.toml file.
        """
    )

    @option(help=requirements_help)
    def requirements(self) -> tuple[str, ...]: ...

    @option(default="uv.lock", help="Path to the lockfile, relative to the build root")
    def lockfile(self) -> str: ...


def rules():
    return [*collect_rules()]
