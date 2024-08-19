# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).
from dataclasses import dataclass
from typing import Tuple

from pants.backend.python.util_rules.pex_cli import PexCliProcess
from pants.engine.internals.native_engine import Digest
from pants.engine.intrinsics import process_request_to_process_result
from pants.engine.process import fallible_to_exec_result_or_raise
from pants.engine.rules import rule, implicitly


@dataclass(frozen=True)
class Lockfile:
    digest: Digest


@dataclass(frozen=True)
class Requirements:
    requirement_strings: Tuple[str, ...]


@rule
async def generate_lockfile(path: str, requirements: Requirements) -> Lockfile:
    pex_proc = PexCliProcess(
        subcommand=("lock", "create", "--style", "strict", "--indent", "2",
                    "--output ", path, *requirements.requirement_strings),
        extra_args=tuple(),
        description=f"Generate lockfile from {len(requirements.requirement_strings)} requirements",
        output_files=(path,)
    )
    fallible_result = await process_request_to_process_result(**implicitly({
        pex_proc: PexCliProcess
    }))
    result = await fallible_to_exec_result_or_raise(fallible_result, **implicitly())
    return Lockfile(digest=result.output_digest)
