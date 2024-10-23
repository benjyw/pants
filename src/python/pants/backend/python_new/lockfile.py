# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import itertools
from dataclasses import dataclass
from typing import Tuple

from pants.backend.python.util_rules.pex_cli import PexCliProcess
from pants.backend.python_new.interpreter import get_interpreter, Interpreter
from pants.backend.python_new.partition import PythonPartition
from pants.engine.fs import PathGlobs
from pants.engine.internals.native_engine import Digest, EMPTY_DIGEST, MergeDigests
from pants.engine.internals.selectors import concurrently
from pants.engine.intrinsics import get_digest_contents, path_globs_to_digest, merge_digests, get_digest_entries
from pants.engine.process import fallible_to_exec_result_or_raise
from pants.engine.rules import rule, implicitly, collect_rules
from pants.util.frozendict import FrozenDict


@dataclass(frozen=True)
class Lockfile:
    digest: Digest


@dataclass(frozen=True)
class Requirements:
    requirement_strings: Tuple[str, ...]
    requirements_txts: Digest


@dataclass(frozen=True)
class LockfileRequest:
    path: str
    interpreter: Interpreter
    requirements: Requirements


@rule
async def generate_lockfile(req: LockfileRequest) -> Lockfile:
    lockfile_path = req.path

    existing_lockfile_digest, req_txt_files, complete_platform_file = await concurrently(
        path_globs_to_digest(PathGlobs([str(lockfile_path)])),
        get_digest_entries(req.requirements.requirements_txts),
        get_digest_entries(req.interpreter.complete_platform.digest)
    )
    input_digest = await merge_digests(MergeDigests([
        existing_lockfile_digest, req.requirements.requirements_txts, req.interpreter.complete_platform.digest
    ]))
    req_strings = [
        *itertools.chain.from_iterable(zip(itertools.repeat("-r", len(req_txt_files)), (file_content.path for file_content in req_txt_files))),
        *req.requirements.requirement_strings,
    ]
    complete_platform = next(iter(complete_platform_file)).path

    pex_args = ["lock", "sync",
                "--lock", lockfile_path,
                "--complete-platform", complete_platform,
                "--style", "strict",
                "--pip-version", "latest",
                "--force-pep517",
                "--indent", "2",
                "--pip-log", "pip.log",
                *req_strings
                ]
    pex_proc = PexCliProcess(
        subcommand=pex_args,
        extra_args=tuple(),
        additional_input_digest=input_digest,
        description=f"Generate {lockfile_path}",
        output_files=(lockfile_path,)
    )
    result = await fallible_to_exec_result_or_raise(**implicitly(
        {pex_proc: PexCliProcess}
    ))
    return Lockfile(digest=result.output_digest)


@rule
async def generate_lockfile_for_partition(partition: PythonPartition) -> Lockfile:
    config = partition.config_or_error()
    interpreter = await get_interpreter("")
    path = config.get_or_error("pants", "lockfile")
    #interpreter_constraints = (config.get_or_error("project", "requires-python"),)
    deps = config.get("project", "dependencies", default=tuple())
    if "dependencies" in config.get("project", "dynamic", tuple()):
        # We support the setuptools-specific dynamic mechanism, as a convenience
        # for handling legacy requirements.txt files.
        deps_files = config.get(
            "tool.setuptools.dynamic", "dependencies", FrozenDict()).get("file", tuple())
        requirements_txts = await path_globs_to_digest(**implicitly({
            PathGlobs(globs=deps_files): PathGlobs
        }))
    else:
        requirements_txts = EMPTY_DIGEST
    return await generate_lockfile(LockfileRequest(
        path=path, interpreter=interpreter,
        requirements=Requirements(requirement_strings=tuple(deps), requirements_txts=requirements_txts))
    )


def rules():
    return collect_rules()
