# Copyright 2021 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import logging
import os
from dataclasses import dataclass

from pants.backend.python.dependency_inference.import_parser import ParsedPythonImports, \
    ParsePythonImportsRequest
from pants.backend.python.target_types import PythonSources
from pants.backend.python.util_rules.pex import PexInterpreterConstraints
from pants.build_graph.address import Address
from pants.core.goals.init import PutativeSourceRoots, PutativeSourceRootsRequest, \
    PutativeSourceRoot
from pants.engine.fs import PathGlobs, Paths
from pants.engine.internals.selectors import Get, MultiGet
from pants.engine.rules import rule, collect_rules
from pants.engine.unions import UnionRule
from pants.python.python_setup import PythonSetup


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PutativePythonSourceRootsRequest:
    pass


@rule
async def find_putative_source_roots(
        req: PutativePythonSourceRootsRequest,
        python_setup: PythonSetup,
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

    return PutativeSourceRoots([
        PutativeSourceRoot(path=f"Found {len(all_py_files.files)} .py files"),
        PutativeSourceRoot(path=f"Found {len(all_imports)} distinct explicit imports"),
    ])


def rules():
    return [
        *collect_rules(),
        UnionRule(PutativeSourceRootsRequest, PutativePythonSourceRootsRequest)
    ]
