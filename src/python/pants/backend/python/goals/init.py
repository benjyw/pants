# Copyright 2021 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Dict, List

from pants.backend.python.dependency_inference.import_parser import ParsedPythonImports, \
    ParsePythonImportsRequest
from pants.backend.python.dependency_inference.module_mapper import ThirdPartyPythonModuleMapping
from pants.backend.python.dependency_inference.python_stdlib.combined import combined_stdlib
from pants.backend.python.target_types import PythonSources, PythonTestsSources, PythonTests, \
    PythonLibrary
from pants.backend.python.util_rules.pex import PexInterpreterConstraints
from pants.base.specs import AddressSpecs, DescendantAddresses
from pants.build_graph.address import Address
from pants.core.goals.init import PutativeSourceRoots, PutativeSourceRootsRequest, \
    PutativeSourceRoot, PutativeTargetsRequest, PutativeTargets, PutativeTarget
from pants.core.util_rules.source_files import SourceFiles, SourceFilesRequest
from pants.engine.fs import PathGlobs, Paths
from pants.engine.internals.selectors import Get, MultiGet
from pants.engine.rules import rule, collect_rules
from pants.engine.target import Targets, Sources
from pants.engine.unions import UnionRule
from pants.python.python_setup import PythonSetup
from pants.source.filespec import Filespec, matches_filespec
from pants.util.frozendict import FrozenDict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PutativePythonTargetsRequest:
    pass


@dataclass(frozen=True)
class PutativePythonSourceRootsRequest:
    pass


def classify_source_files(paths: Iterable[str]) -> Dict[str, List[str]]:
    """Returns a dict of target type alias -> files that belong to targets of that type."""
    tests_filespec = Filespec(includes=PythonTestsSources.default)
    test_files = set(matches_filespec(tests_filespec, paths=paths))
    library_files = set(paths) - test_files
    return {
        PythonTests.alias: list(test_files),
        PythonLibrary.alias: list(library_files)
    }


def group_by_dir(paths: Iterable[str]) -> Dict[str, List[str]]:
    """For a list of file paths, returns a dict of directory path -> files in that dir."""
    ret = defaultdict(list)
    for path in paths:
        dirname, filename = os.path.split(path)
        ret[dirname].append(filename)
    return ret


@rule
async def find_putative_targets(
        req: PutativePythonTargetsRequest,
) -> PutativeTargets:
    all_tgts = await Get(Targets, AddressSpecs([DescendantAddresses("")]))
    all_owned_sources = await Get(
        SourceFiles, SourceFilesRequest([tgt.get(Sources) for tgt in all_tgts])
    )

    all_py_files = await Get(Paths, PathGlobs(["**/*.py"]))
    unowned_py_files = set(all_py_files.files) - set(all_owned_sources.files)
    classified_unowned_py_files = classify_source_files(unowned_py_files)
    pts = []
    for tgt_type, paths in classified_unowned_py_files.items():
        for dirname, filenames in group_by_dir(paths).items():
            name = "tests" if tgt_type == PythonTests.alias else os.path.basename(dirname)
            kwargs = {"name": name} if  tgt_type == PythonTests.alias else {}
            pts.append(PutativeTarget(type_alias=tgt_type, path=dirname,
                                      name=name, sources=tuple(sorted(filenames)),
                                      kwargs=FrozenDict(kwargs)))
    return PutativeTargets(pts)


@rule
async def find_putative_source_roots(
        req: PutativePythonSourceRootsRequest,
        python_setup: PythonSetup,
        third_party_mapping: ThirdPartyPythonModuleMapping,
) -> PutativeSourceRoots:
    all_py_files = await Get(Paths, PathGlobs(["**/*.py"]))
    imports_iter = await MultiGet(
        Get(
            ParsedPythonImports,
            ParsePythonImportsRequest(
                PythonSources(
                    raw_value=[os.path.basename(path)],
                    address=Address(os.path.dirname(path))
                ),
                PexInterpreterConstraints(python_setup.interpreter_constraints),
            ),
        ) for path in all_py_files.files)

    all_imports = set()
    for imports in imports_iter:
        all_imports.update(imports.explicit_imports)

    external_modules = set(combined_stdlib) | set(third_party_mapping.keys()) | {"__future__"}

    def is_external_import(imp: str) -> bool:
        parts = imp.split(".")
        module_str = ""
        for part in parts:
            module_str = f"{module_str}.{part}" if module_str else part
            if module_str in external_modules:
                return True
        return False

    first_party_imports = {imp for imp in all_imports if not is_external_import(imp)}
    logger.error("QQQQQQQQQQQQQQQQ")
    for imp in sorted(first_party_imports):
        logger.error(imp)

    return PutativeSourceRoots([
        PutativeSourceRoot(path=f"Found {len(all_py_files.files)} .py files"),
        PutativeSourceRoot(path=f"Found {len(all_imports)} distinct explicit imports"),
    ])


def rules():
    return [
        *collect_rules(),
        UnionRule(PutativeTargetsRequest, PutativePythonTargetsRequest),
        UnionRule(PutativeSourceRootsRequest, PutativePythonSourceRootsRequest),
    ]
