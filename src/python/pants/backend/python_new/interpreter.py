# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).
import logging
import os
from dataclasses import dataclass

from pants.backend.python.util_rules.pex_cli import PexCliProcess
from pants.backend.python_new.subsystems import PythonSettings
from pants.engine.internals.native_engine import Digest
from pants.engine.platform import Platform
from pants.engine.process import fallible_to_exec_result_or_raise
from pants.engine.rules import rule, collect_rules, implicitly


@dataclass(frozen=True)
class InterpreterConstraint:
    constraint: str


@dataclass(frozen=True)
class InterpreterVersion:
    version: str


@dataclass(frozen=True)
class CompletePlatform:
    digest: Digest


def complete_platform_path(name: str, python_settings: PythonSettings) -> str:
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
