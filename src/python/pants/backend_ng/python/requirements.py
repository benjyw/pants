# Copyright 2025 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from dataclasses import dataclass
import tomllib

import requirements

from pants.backend_ng.python.project import PythonProject
from pants.engine.intrinsics import get_file_contents
from pants.engine.rules import collect_rules, rule


@dataclass(frozen=True)
class RequirementsRequest:
    """
    A set of requirement inputs.

    Each value can have one of the following formats:
    - A requirement string.
      - Directly specifies a requirement.
    - `@path/to/requirements.txt` (or any name ending in .txt)
      - Refers to the requirement strings in the .txt file.
    - `@path/to/pyproject.toml:dependencies.list.location` (or any name ending in .toml)
        - Refers to the contents of the specified table in the .toml file.
    - `@path/to/pyproject.toml` (or any name ending in .toml)
        - Refers to the contents of the <default_pyproject_toml_table> in the .toml file. 
    """
    input_strings: tuple[str, ...]
    default_pyproject_toml_table: str


@dataclass(frozen=True)
class Requirements:
    requirement_strings: tuple[str, ...]


@rule
async def get_requirements(req: RequirementsRequest) -> Requirements:
    req_strs = []
    for val in req.input_strings:
        if val.startswith("@"):
            file_val = val[1:]
            if file_val.endswith(".txt"):
                contents = (await get_file_contents(file_val)).decode()
                req_strs.extend(requirements.parse(contents))
            else:
                path, _, location = file_val.partition(":")
                location = location or req.default_pyproject_toml_table
                contents = (await get_file_contents(path)).decode()
                entry = tomllib.loads(contents)
                for name in location.split("."):
                    entry = entry.get(name)
                    if entry is None:
                        raise Exception(f"{location} in {path} not found")
                dep_list = entry
                if not isinstance(dep_list, list):
                    raise Exception(
                        f"Expected {location} in {path} to be a list of dependencies, "
                        f"but it was a {type(dep_list)}"
                    )
                req_strs.extend(str(dep) for dep in dep_list)
        else:
            req_strs.append(val)

    return Requirements(requirement_strings=req_strs)


@rule
async def get_project_requirements(python_options: PythonProject) -> Requirements:
    return await get_requirements(RequirementsRequest(python_options.requirements(), "project.dependencies"))


def rules():
    return [*collect_rules()]
