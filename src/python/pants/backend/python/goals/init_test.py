# Copyright 2021 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.backend.python.goals.init import classify_source_files, group_by_dir
from pants.backend.python.target_types import PythonTests, PythonLibrary


def test_classify_source_files():
    test_files = {"foo/bar/baz_test.py", "foo/test_bar.py", "foo/tests.py", "conftest.py",
                  "foo/bar/baz_test.pyi", "foo/test_bar.pyi", "tests.pyi"}
    lib_files = {"foo/bar/baz.py", "foo/bar_baz.py", "foo.pyi"}


    assert {
      PythonTests.alias: test_files,
      PythonLibrary.alias: lib_files
    } == classify_source_files(test_files | lib_files)


def test_group_by_dir():
    paths = {"foo/bar/baz1.py", "foo/bar/baz1_test.py", "foo/bar/qux/quux1.py",
             "foo/__init__.py", "foo/bar/__init__.py", "foo/bar/baz2.py",
             "foo/bar1.py", "foo1.py", "__init__.py"}
    assert {
        "": {"__init__.py", "foo1.py"},
        "foo": {"__init__.py", "bar1.py"},
        "foo/bar": {"__init__.py", "baz1.py", "baz1_test.py", "baz2.py"},
        "foo/bar/qux": {"quux1.py"},
    } == group_by_dir(paths)
