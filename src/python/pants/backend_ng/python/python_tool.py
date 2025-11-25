# Copyright 2026 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.backend_ng.python.requirements import RequirementsRequest
from pants.engine.rules import collect_rules
from pants.ng.subsystem import ContextualSubsystem, option
from pants.util.strutil import softwrap


# mypy: disable-error-code=empty-body


class PythonTool(ContextualSubsystem):
    @classmethod
    def help(cls):
        return f"Options for the {cls.options_scope} tool"

    @classmethod
    def requirements_help(cls):
        return softwrap(
            f"""
            3rd-party requirements for the {cls.options_scope} tool. Each value can have one of the following formats:
            - A requirement string.
            - `@path/to/requirements.txt` (or any name ending in .txt)
            - `@path/to/pyproject.toml` (or any name ending in .toml)
            - will take the contents of the `dependency-groups.<toolname>` list
            - `@path/to/pyproject.toml:dependencies.list.location` (or any name ending in .toml)
        """
    )

    @option(required=True, help=requirements_help)
    def requirements(self) -> tuple[str, ...]: ...

    def requirements_request(self) -> RequirementsRequest:
        return RequirementsRequest(self.requirements(), f"dependency-groups.{self.options_scope}")


class IsolatedTool(PythonTool):
    """A tool that runs in its own virtualenv, separate from the project's dependencies.

    Used for tools that don't import code from the project but act on it as text.
    
    Its requirements may clash with those of the project.
    """
    ...


class ProjectTool(PythonTool):
    """A tool that runs in the same virtualenv as the project's dependencies.

    Used for tools that import code from the project (e.g., for running tests or typechecking).
    
    Its requirements must not clash with those of the project, so they can coexist in
    a single lockfile.
    """


def rules():
    return [*collect_rules()]