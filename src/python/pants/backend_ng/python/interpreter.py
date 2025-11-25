# Copyright 2025 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from dataclasses import dataclass
import os
from pathlib import Path

from pants.backend_ng.python.project import get_interpreter_version
from pants.backend_ng.python.uv import UV_APPEND_ONLY_CACHES, UvProcess, execute_uv_process
from pants.engine.internals.native_engine import EMPTY_DIGEST, Digest
from pants.engine.process import Process, ProcessResult, execute_process_or_raise
from pants.engine.rules import collect_rules, implicitly, rule
from pants.util.frozendict import FrozenDict


@dataclass(frozen=True)
class PythonInterpreter:
    version: str
    exe: Path


@dataclass(frozen=True)
class PythonProcess:
    description: str
    interpreter: PythonInterpreter
    python_args: tuple[str, ...]
    input_digest: Digest | None = None
    extra_env: FrozenDict | None = None


@rule
async def get_interpreter() -> PythonInterpreter:
    interpreter_version = await get_interpreter_version(**implicitly())
    # Install the interpreter into the named cache (or verify that it exists).
    uv_result = await execute_uv_process(UvProcess(
        "Install interpreter",
        (
            "python", "install",
            "--no-config", "--no-registry", "--no-bin",
            interpreter_version
        ),
        None,
    ))

    # Find the interpreter we just installed, and also echo the PWD of the sandbox,
    # so we can get the relpath of the interpreter. This is a valid relpath in any
    # sandbox that has the appropriate named cache mounted.
    uv_result = await execute_uv_process(UvProcess(
        "Locate install interpreter",
        (
            "python", "find",
            "--managed-python",
            interpreter_version
        ),
        None,
        in_shell=True,
        post_command="echo ${PWD}",
    ))
    full_interpreter_path, _, sandbox_dir = uv_result.process_result.stdout.decode().strip().partition("\n")
    rel_interpreter_path = os.path.relpath(
        os.path.realpath(full_interpreter_path),
        os.path.realpath(sandbox_dir)
    )
    return PythonInterpreter(version=interpreter_version, exe=Path(rel_interpreter_path))


@rule
async def execute_python_process(python_process: PythonProcess) -> ProcessResult:
    process = Process(
        argv=[str(python_process.interpreter.exe), *python_process.python_args],
        description=python_process.description,
        input_digest=python_process.input_digest or EMPTY_DIGEST,
        env=python_process.extra_env,
        append_only_caches=UV_APPEND_ONLY_CACHES,
    )
    result = await execute_process_or_raise(**implicitly({process: Process}))
    return result


def rules():
    return [*collect_rules()]
