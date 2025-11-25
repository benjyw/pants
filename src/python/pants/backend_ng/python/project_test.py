# Copyright 2026 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from textwrap import dedent

from pants.backend_ng.python.project import PythonProject
from pants.engine.internals.native_engine import PyConfigSource, PyNgOptionsReader
from pants.util.contextutil import pushd


def test_interpreter_version(tmp_path) -> None:
    with pushd(tmp_path):
        with open("pyproject.toml", "w") as fp:
            fp.write(
                dedent("""
                [project]
                requires-python = "==4.5.999"
                """)
            )
        PythonProject._initialize_()
        pyproject = PythonProject.create(
            PyNgOptionsReader(
                buildroot=tmp_path,
                flags={},
                env={},
                configs=[
                    PyConfigSource(
                        "pants.toml",
                        dedent("""
                               [pyproject]
                               interpreter_version = "@pyproject.toml:project.requires-python"
                        """).encode(),
                    ),
                ],
            )
        )
        assert pyproject.interpreter_version == "==4.5.999"


def test_requirements(tmp_path) -> None:
    with pushd(tmp_path):
        with open("pyproject.toml", "w") as fp:
            fp.write(
                dedent("""
                [project]
                dependencies = [
                       "cowsay>=5.0,<7",
                       "ansicolor==1.1.8",
                ]
                """)
            )
        PythonProject._initialize_()
        pyproject = PythonProject.create(
            PyNgOptionsReader(
                buildroot=tmp_path,
                flags={},
                env={},
                configs=[
                    PyConfigSource(
                        "pants.toml",
                        dedent("""
                               [pyproject]
                               interpreter_version = "9.8.7"
                               requirements = "@pyproject.toml:project.dependencies"
                        """).encode(),
                    ),
                ],
            )
        )
        assert pyproject.requirements == ("cowsay>=5.0,<7", "ansicolor==1.1.8")
