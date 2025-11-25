# Copyright 2026 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from dataclasses import dataclass
import os
from pathlib import Path
import logging
from pants.backend.build_files.utils import collect_rules
from pants.backend.python.dependency_inference.parse_python_dependencies import ParsePythonDependenciesRequest, parse_python_dependencies
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
        os.path.sep.join((*path_parts[0:-1], "__init__.py")),
    ]


@rule(desc="Find transitive deps")
async def find_transitive_deps(source_paths: SourcePaths) -> TransitiveDeps:
    # TODO: We really should use Path in more places, but doing so efficiently here
    #  would require changes to Snapshot et al.
    visited = set()
    to_visit = set(str(path) for path in source_paths.paths)
    nonexistent = set()

    while to_visit:
        # Look inside the Python sources to find imports or infer-dep pragmas.
        # TODO: Handle imports/pragmas in other files? Some registration of
        #   file suffix to import parser? Then we can seamlessly traverse deps
        #   across languages etc.
        python_sources_snapshot = await digest_to_snapshot(**implicitly(
            PathGlobs(
                globs=tuple(str(path) for path in to_visit if path.endswith(".py") or path.endswith(".pyi")),
                glob_match_error_behavior=GlobMatchErrorBehavior.ignore,
                conjunction=GlobExpansionConjunction.all_match,
            )
        ))
        files_deps = await parse_python_dependencies(
                ParsePythonDependenciesRequest(
                    SourceFiles(snapshot=python_sources_snapshot, unrooted_files=tuple(),
                )
            ), **implicitly()
        )
        discovered_deps = OrderedSet()
        candidate_paths = set()
        for source_path, file_deps in files_deps.path_to_deps.items():
            source_dir = os.path.dirname(source_path)
            # We'll turn these symbols into paths after this loop, and therefore after de-duping.
            discovered_deps.update(file_deps.imports.keys())
            # Add in the files inferred via the infer-dep pragma. These don't have to themselves
            # be Python files. But if they are they will be parsed for deps in the next iteration.
            candidate_paths.update(os.path.join(source_paths.source_root.path, source_dir, key) for key in file_deps.explicit_dependencies.keys())

        for dep in discovered_deps:
            candidate_paths.update(_symbol_to_candidate_paths(source_paths.source_root, dep))

        # We may have already encountered some of these paths and know they don't exist,
        # so we can ignore them.
        candidate_paths -= nonexistent

        candidate_paths_that_exist = set(
            (await path_globs_to_paths(PathGlobs(
                globs=tuple(tuple(sorted(candidate_paths))),
                glob_match_error_behavior=GlobMatchErrorBehavior.ignore,
                conjunction=GlobExpansionConjunction.all_match,
            ))).files
        )
        nonexistent.update(candidate_paths - candidate_paths_that_exist)
        visited.update(to_visit)
        to_visit = set(candidate_paths_that_exist) - visited

    return TransitiveDeps(tuple(Path(path) for path in visited))


def rules():
    return [*collect_rules()]
