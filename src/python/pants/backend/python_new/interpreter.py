# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import os
from dataclasses import dataclass

from pants.backend.python.util_rules.pex_cli import PexCliProcess
from pants.backend.python_new.subsystems import PythonSettings
from pants.engine.fs import EMPTY_DIGEST, PathGlobs
from pants.engine.internals.native_engine import Digest
from pants.engine.intrinsics import path_globs_to_digest
from pants.engine.platform import Platform
from pants.engine.process import fallible_to_exec_result_or_raise
from pants.engine.rules import rule, collect_rules, implicitly


@dataclass(frozen=True)
class InterpreterConstraint:
    constraint: str


@dataclass(frozen=True)
class CompletePlatform:
    digest: Digest


@dataclass(frozen=True)
class Interpreter:
    complete_platform: CompletePlatform


@rule
async def get_interpreter(name: str, python_settings: PythonSettings) -> Interpreter:
    complete_platform_path = get_complete_platform_path(name, python_settings)
    complete_platform_digest = await path_globs_to_digest(PathGlobs([]))
    if complete_platform_digest == EMPTY_DIGEST:
        raise Exception(f"No complete platform file found at {complete_platform_path}. Run `pants inspect-interpreters` to create one.")
    else:
        complete_platform = CompletePlatform(complete_platform_digest)
    return Interpreter(complete_platform)


def get_complete_platform_path(name: str, python_settings: PythonSettings) -> str:
    local_platform = Platform.create_for_localhost()
    return os.path.join(python_settings.settings_dir, "interpreters", f"{name}.{local_platform.name}.json")


@rule
async def generate_complete_platform(output_path: str, ic: InterpreterConstraint) -> CompletePlatform:
    pex_args = ["interpreter", "inspect", "--markers", "--tags", "--indent", "2",
                "--interpreter-constraint", ic.constraint,
                "--output", output_path]
    pex_proc = PexCliProcess(
        subcommand=pex_args,
        extra_args=tuple(),
        description=f"Generate complete platforms for Python {ic}",
        output_files=(output_path,)
    )
    result = await fallible_to_exec_result_or_raise(**implicitly(
        {pex_proc: PexCliProcess}
    ))

    return CompletePlatform(digest=result.output_digest)


def rules():
    return collect_rules()
