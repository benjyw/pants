# Copyright 2025 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from dataclasses import dataclass
import dataclasses
from pathlib import Path
import shlex
from pants.backend_ng.python.project import PythonProject
from pants.base.glob_match_error_behavior import GlobMatchErrorBehavior
from pants.core.util_rules.external_tool import download_external_tool
from pants.engine.fs import CreateDigest, GlobExpansionConjunction, PathGlobs
from pants.engine.internals.native_engine import Digest, MergeDigests
from pants.engine.intrinsics import create_digest, execute_process, get_digest_entries, merge_digests, path_globs_to_digest
from pants.engine.process import Process
from pants.engine.rules import collect_rules, concurrently, implicitly, rule
from pants.ng.external_binary import ExternalBinary
from pants.ng.source_partition import SourcePaths
from pants.ng.system import System
from pants.source.source_root import SourceRootsRequest, get_optional_source_roots
from pants.util.frozendict import FrozenDict
from pants.util.logging import LogLevel
from pants.util.meta import classproperty
from pants.util.strutil import Simplifier, softwrap


class Uv(ExternalBinary):
    options_scope = "uv"

    help = "The uv tool"

    version_default ="0.9.25"

    @classproperty
    def exe_default(cls):

        return "uv"

    known_versions_default= softwrap(
        """
        {
            "0.9.25": {
                "linux_x86_64": {
                    "url": "https://github.com/astral-sh/uv/releases/download/0.9.25/uv-x86_64-unknown-linux-gnu.tar.gz",
                    "sha256": "fa1f4abfe101d43e820342210c3c6854028703770f81e95b119ed1e65ec81b35",
                    "size": 22335909
                },
                "linux_arm64": {
                    "url": "https://github.com/astral-sh/uv/releases/download/0.9.25/uv-aarch64-unknown-linux-gnu.tar.gz",
                    "sha256": "a8f1d71a42c4470251a880348b2d28d530018693324175084fa1749d267c98c6",
                    "size": 21011132
                },
                "macos_arm64": {
                    "url": "https://github.com/astral-sh/uv/releases/download/0.9.25/uv-aarch64-apple-darwin.tar.gz",
                    "sha256": "606b3c6949d971709f2526fa0d9f0fd23ccf60e09f117999b406b424af18a6a6",
                    "size": 19127886
                }
            }
        }
        """
    )


@dataclass(frozen=True)
class UvProcess:
    description: str
    uv_args: tuple[str, ...]
    source_roots: tuple[str, ...] = tuple()
    input_digest: Digest | None = None
    extra_env: FrozenDict | None = None
    in_shell: bool = False
    post_command: str | None = None
    output_directories: tuple[str, ...] = tuple()
    output_files: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class UvProcessResult:
    description: str
    exit_code: int
    stdout: str
    stderr: str
    input_digest: Digest
    output_digest: Digest
    # A uv process may incidentally update the lockfile as a side-effect, so we always capture it,
    # separated out from the output digest.
    lockfile_digest: Digest

    # The engine displays the rule as "<rule.desc> - <result.metadata.desc>".
    # So this will render as, e.g., "Lint - `run ruff check` running on... succeeded"
    def message(self) -> str:
        message = self.description
        message += (
            " succeeded." if self.exit_code == 0 else f" failed (exit code {self.exit_code})."
        )
        if self.stdout:
            message += f"\n{self.stdout}"
        if self.exit_code and self.stderr:
            message += f"\n{self.stderr}"

        return message


# See https://docs.astral.sh/uv/reference/storage/.
# Note that we can't use the XDG_* env vars because those must be abspaths, and we don't
# know the path to the sandbox (and through it to the named cache).
# But uv falls back to paths computed from $HOME, and that works with a relpath.
_UV_HOME = Path(".uv_home")
UV_APPEND_ONLY_CACHES = FrozenDict({"uv": str(_UV_HOME)})

_UV_LOCK = "uv.lock"
_PYPROJECT_TOML = "pyproject.toml"


@rule
async def execute_uv_process(uv_process: UvProcess, system: System, python: PythonProject, uv: Uv) -> UvProcessResult:
    downloaded_uv, project_config_digest = await concurrently(
        download_external_tool(uv.get_download_request()),
        path_globs_to_digest(
            PathGlobs(
                globs=(python.project(), python.lockfile()),
                glob_match_error_behavior=GlobMatchErrorBehavior.ignore,  # The lockfile might not exist yet.
                conjunction=GlobExpansionConjunction.any_match,
            )
        )
    )

    # TODO: Currently all uv processes run against the entire pyproject.toml.
    #  This means that we'll invalidate the cache more aggressively than we need to, e.g.,
    #  when pyproject.toml changes in a way that does not affect the specific operation.
    #  If this becomes an issue for users we can consider finessing this.

    if python.lockfile != _UV_LOCK or python.project != _PYPROJECT_TOML:
        # Put the config and lockfile where uv expects them.
        project_config_entries = await get_digest_entries(project_config_digest)
        relocated_entries = []
        for entry in project_config_entries:
            if entry.path == python.project():
                relocated_entries.append(dataclasses.replace(entry, path=_PYPROJECT_TOML))
            elif entry.path == python.lockfile():
                relocated_entries.append(dataclasses.replace(entry, path=_UV_LOCK))
        project_config_digest = await create_digest(CreateDigest(relocated_entries))

    digests = [downloaded_uv.digest, project_config_digest]
    if uv_process.input_digest:
        digests.append(uv_process.input_digest)
    input_digest = await merge_digests(MergeDigests(tuple(digests)))

    args=[downloaded_uv.exe, *uv_process.uv_args]

    if uv_process.in_shell:
        args_str = shlex.join(args)
        sh_script = (
            args_str if uv_process.post_command is None
            else f"{args_str} && {uv_process.post_command}"
        )
        args = [system.sh_path(), "-c", sh_script]
    else:
        if uv_process.post_command:
            raise ValueError("UvProcess.post_command is set, so in_shell must be True")

    env = FrozenDict({
        "PATH": ".",
        "HOME": str(_UV_HOME),
        "PYTHONPATH": ":".join(uv_process.source_roots),
        **(uv_process.extra_env or {}),
    })
    process = Process(
        argv=args,
        level=LogLevel.DEBUG,
        description=uv_process.description,
        input_digest=input_digest,
        env=env,
        append_only_caches=UV_APPEND_ONLY_CACHES,
        output_directories=uv_process.output_directories,
        output_files=(_UV_LOCK, *uv_process.output_files)
    )
    result = await execute_process(**implicitly({process: Process}))

    # Fish the lockfile out of the output digest.
    output_entries  = await get_digest_entries(result.output_digest)
    other_output_entries = []
    lockfile_entry = None
    for entry in output_entries:
        if entry.path == _UV_LOCK:
            # Relocate the lockfile back to its location in the repo.
            lockfile_entry = dataclasses.replace(entry, path=python.lockfile())
        else:
            other_output_entries.append(entry)

    lockfile_digest, output_digest = await concurrently(
        create_digest(CreateDigest([lockfile_entry] if lockfile_entry else [])),
        create_digest(CreateDigest(other_output_entries))
    )

    simplifier = Simplifier()

    return UvProcessResult(
        description=uv_process.description,
        exit_code = result.exit_code,
        stdout=simplifier.simplify(result.stdout.decode()),
        stderr=simplifier.simplify(result.stderr.decode()),
        input_digest=input_digest,
        output_digest=output_digest,
        lockfile_digest=lockfile_digest
    )


@dataclass(frozen=True)
class UvCommand:
    """A higher level abstraction around a UvProcess."""
    # We append " on x files under <dir>" to this prefix to generate the process description.
    description_prefix: str
    uv_args: tuple[str, ...]
    source_paths: SourcePaths
    extra_input_digest: Digest


@rule(desc="Run uv on partition")
async def execute_uv_command(uv_command: UvCommand) -> UvProcessResult:
    source_path_strs = tuple(str(path) for path in uv_command.source_paths.paths)
    sources_digest = await path_globs_to_digest(PathGlobs(
        source_path_strs,
        glob_match_error_behavior=GlobMatchErrorBehavior.error,
        conjunction=GlobExpansionConjunction.all_match,
        description_of_origin="Input sources for a uv command",
    ))
    input_digest = await merge_digests(MergeDigests((sources_digest, uv_command.extra_input_digest)))

    optional_source_roots_res = await get_optional_source_roots(SourceRootsRequest.for_files(source_path_strs))
    distinct_source_roots = tuple(sorted(set(osr.source_root.path for osr in optional_source_roots_res.path_to_optional_root.values() if osr.source_root is not None)))

    descr_suffix = (
        f"{source_path_strs[0]}" if len(source_path_strs) == 1 else
        f"{len(source_path_strs)} files under {uv_command.source_paths.commondir()}"
    )

    uv_args = list(uv_command.uv_args)
    uv_args.extend(source_path_strs)

    ruff_process = UvProcess(
        description=f"{uv_command.description_prefix} on {descr_suffix}",
        uv_args=tuple(uv_args),
        source_roots=distinct_source_roots,
        input_digest=input_digest,
        output_files=source_path_strs,
    )
    return await execute_uv_process(ruff_process, **implicitly())


def rules():
    return [*collect_rules()]




# uv_process = UvProcess(description="Run uv with no args", uv_args=tuple(), input_digest=None)
# uv_result = await execute_uv(uv_process, **implicitly())
# interpreter = await get_interpreter(**implicitly())
# reqs = await get_project_requirements(**implicitly())
# py_proc_res = await execute_python_process(PythonProcess(
#     description="Run python",
#     interpreter=interpreter,
#     python_args=("--version",),
# ))
#ruff_reqs = await get_requirements(ruff.requirements_request())

