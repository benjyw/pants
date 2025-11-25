# Copyright 2026 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from pants.backend.build_files.utils import collect_rules
from pants.backend.python.dependency_inference.parse_python_dependencies import (
    ParsePythonDependenciesRequest,
    parse_python_dependencies,
)
from pants.base.build_root import BuildRoot
from pants.base.glob_match_error_behavior import GlobMatchErrorBehavior
from pants.core.util_rules.source_files import SourceFiles
from pants.engine.fs import GlobExpansionConjunction, PathGlobs
from pants.engine.intrinsics import digest_to_snapshot, path_globs_to_paths
from pants.engine.rules import implicitly, rule
from pants.ng.source_partition import SourcePaths
from pants.source.source_root import SourceRoot
from pants.util.ordered_set import OrderedSet

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransitiveDeps:
    paths: tuple[str, ...]


def _symbol_to_candidate_paths(source_root: SourceRoot, symbol: str) -> tuple[str, ...]:
    """Files that might provide the dotted-string symbol.

    Which file actually does provide the symbol depends on the existence and content
    of the relevant __init__.py.
    """
    dep_parts = symbol.split(".")
    if len(dep_parts) == 1:
        return []  # This is (almost certainly) a third-party or stdlib symbol.
    path_parts = [source_root.path, *dep_parts]
    dep_module_path = os.path.sep.join(path_parts) + ".py"
    dep_parent_module_path = os.path.sep.join(path_parts[0:-1]) + ".py"

    return [
        dep_module_path,
        dep_module_path + "i",
        dep_parent_module_path,
        dep_parent_module_path + "i",
        os.path.sep.join((*path_parts, "__init__.py")),
        os.path.sep.join((*path_parts[0:-1], "__init__.py")),
    ]


@rule(desc="Find transitive deps")
async def find_transitive_deps(source_paths: SourcePaths, build_root: BuildRoot) -> TransitiveDeps:
    # TODO: We really should use Path in more places, but doing so efficiently here
    #  would require changes to Snapshot et al.
    visited_paths = set()
    paths_to_visit = set(str(path) for path in source_paths.paths)
    nonexistent_paths = set()

    while paths_to_visit:
        # Look inside the Python sources to find imports or infer-dep pragmas.
        # TODO: Handle imports/pragmas in other files? Some registration of
        #   file suffix to import parser? Then we can seamlessly traverse deps
        #   across languages etc.
        python_sources_snapshot = await digest_to_snapshot(
            **implicitly(
                PathGlobs(
                    globs=tuple(
                        str(path)
                        for path in paths_to_visit
                        if path.endswith(".py") or path.endswith(".pyi")
                    ),
                    glob_match_error_behavior=GlobMatchErrorBehavior.ignore,
                    conjunction=GlobExpansionConjunction.all_match,
                )
            )
        )
        files_deps = await parse_python_dependencies(
            ParsePythonDependenciesRequest(
                SourceFiles(
                    snapshot=python_sources_snapshot,
                    unrooted_files=tuple(),
                )
            ),
            **implicitly(),
        )
        discovered_deps = OrderedSet()
        candidate_path_globs = set()
        for source_path, file_deps in files_deps.path_to_deps.items():
            source_dir = os.path.dirname(source_path)
            # We'll turn these symbols into paths after this loop, and therefore after de-duping.
            discovered_deps.update(file_deps.imports.keys())
            # Add in the files inferred via the infer-dep pragma. These don't have to themselves
            # be Python files. But if they are they will be parsed for deps in the next iteration.
            # Absolute paths are taken from the repo root. Relative paths are relative to the
            # file with the pragma.
            explicit_dep_globs = tuple(
                os.path.normpath(key[1:])
                if key.startswith("/")
                else os.path.normpath(os.path.join(source_paths.source_root.path, source_dir, key))
                for key in file_deps.explicit_dependencies.keys()
            )
            explicit_deps_that_escape = tuple(
                glob for glob in explicit_dep_globs if glob.startswith(".")
            )
            if explicit_deps_that_escape:
                raise Exception(
                    f"Found explicit dependency pragmas (`# pants: infer-dep(...)` for files outside the build root: {explicit_deps_that_escape}"
                )
            candidate_path_globs.update(explicit_dep_globs)

        for dep in discovered_deps:
            candidate_path_globs.update(_symbol_to_candidate_paths(source_paths.source_root, dep))

        # Many of the globs are likely to be single paths (without wildcards), so it's worth
        # ignoring the ones that we know don't exist.
        candidate_path_globs -= nonexistent_paths

        candidate_paths_that_exist = set(
            (
                await path_globs_to_paths(
                    PathGlobs(
                        globs=tuple(tuple(sorted(candidate_path_globs))),
                        glob_match_error_behavior=GlobMatchErrorBehavior.ignore,
                        conjunction=GlobExpansionConjunction.all_match,
                    )
                )
            ).files
        )
        nonexistent_paths.update(candidate_path_globs - candidate_paths_that_exist)
        visited_paths.update(paths_to_visit)
        paths_to_visit = set(candidate_paths_that_exist) - visited_paths

    return TransitiveDeps(tuple(Path(path) for path in visited_paths))


def rules():
    return [*collect_rules()]
