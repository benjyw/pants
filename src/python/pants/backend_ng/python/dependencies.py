# Copyright 2026 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from dataclasses import dataclass
from pathlib import Path
import logging
from pants.backend.build_files.utils import collect_rules
from pants.backend.python.dependency_inference.parse_python_dependencies import ParsePythonDependenciesRequest, parse_python_dependencies
from pants.base.glob_match_error_behavior import GlobMatchErrorBehavior
from pants.core.util_rules.source_files import SourceFiles
from pants.engine.fs import GlobExpansionConjunction, PathGlobs
from pants.engine.intrinsics import digest_to_snapshot
from pants.engine.rules import implicitly, rule
from pants.ng.source_partition import SourcePaths
from pants.util.ordered_set import OrderedSet

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransitiveDeps:
    paths: tuple[str, ...]


@rule(desc="Find transitive deps")
async def find_transitive_deps(source_paths: SourcePaths) -> TransitiveDeps:
    # TODO: We really should use Path in more places, but doing so efficiently here
    #  would require changes to Snapshot et al.
    visited: OrderedSet[str] = OrderedSet()
    to_visit: OrderedSet[str] = OrderedSet(str(path) for path in source_paths.paths)

    while to_visit:
        logger.warning(f"XXXXXXXXX {to_visit}")
        source_snapshot = await digest_to_snapshot(**implicitly(
            PathGlobs(
                globs=tuple(str(path) for path in to_visit),
                glob_match_error_behavior=GlobMatchErrorBehavior.ignore,
                conjunction=GlobExpansionConjunction.all_match,
            )
        ))
        files_deps = await parse_python_dependencies(
                ParsePythonDependenciesRequest(
                    SourceFiles(snapshot=source_snapshot, unrooted_files=tuple(),
                )
            ), **implicitly()
        )
        discovered_deps = OrderedSet()
        for file_deps in files_deps.path_to_deps.values():
            discovered_deps.update(file_deps.imports.keys())

        visited.update(to_visit)
        to_visit = discovered_deps - visited
    return TransitiveDeps(tuple(Path(path) for path in visited))


def rules():
    return [*collect_rules()]
