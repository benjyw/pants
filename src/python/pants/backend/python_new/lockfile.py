# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).
import itertools
import logging
from dataclasses import dataclass
from typing import Tuple

from pants.backend.python.util_rules.pex_cli import PexCliProcess
from pants.backend.python_new.partition import PythonPartition
from pants.engine.fs import PathGlobs
from pants.engine.internals.native_engine import Digest
from pants.engine.intrinsics import directory_digest_to_digest_contents
from pants.engine.process import fallible_to_exec_result_or_raise
from pants.engine.rules import rule, implicitly, collect_rules
from pants.util.frozendict import FrozenDict


@dataclass(frozen=True)
class Lockfile:
    digest: Digest


@dataclass(frozen=True)
class Requirements:
    requirement_strings: Tuple[str, ...]


@dataclass(frozen=True)
class LockfileRequest:
    path: str
    interpreter_constraints: Tuple[str, ...]
    requirements: Requirements


@rule
async def generate_lockfile(req: LockfileRequest) -> Lockfile:
    path = req.path
    req_strings = req.requirements.requirement_strings

    ic_args = itertools.chain.from_iterable(["--interpreter-constraint", ic] for ic in req.interpreter_constraints)
    pex_proc = PexCliProcess(
        subcommand=("lock", "create", "--style", "strict",
                    *ic_args,
                    "--force-pep517",
                    "--indent", "2",
                    "--output", path, *req_strings),
        extra_args=tuple(),
        description=f"Generate lockfile from {len(req_strings)} requirements",
        output_files=(path,)
    )
    result = await fallible_to_exec_result_or_raise(**implicitly(
        {pex_proc: PexCliProcess}
    ))
    return Lockfile(digest=result.output_digest)


@rule
async def generate_lockfile_for_partition(partition: PythonPartition) -> Lockfile:
    config = partition.config_or_error()
    path = config.get_or_error("pants", "lockfile")
    interpreter_constraints = (config.get_or_error("project", "requires-python"),)
    deps = config.get("project", "dependencies")
    if deps is None:
        if "dependencies" in config.get("project", "dynamic", tuple()):
            # We support the setuptools-specific dynamic mechanism, as a convenience
            # for handling legacy requirements.txt files.
            deps_files = config.get(
                "tool.setuptools.dynamic", "dependencies", FrozenDict()).get("file", tuple())
            deps_files_contents = await directory_digest_to_digest_contents(**implicitly({
                PathGlobs(globs=deps_files): PathGlobs
            }))
            deps = tuple(itertools.chain.from_iterable(fc.content.decode().splitlines(keepends=False) for fc in deps_files_contents))
        else:
            deps = []
    return await generate_lockfile(LockfileRequest(
        path=path, interpreter_constraints=interpreter_constraints,
        requirements=Requirements(requirement_strings=tuple(deps)))
    )


def rules():
    return collect_rules()
