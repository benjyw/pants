# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

python_library()

python_tests(
  name='tests',
  dependencies=[
    'src/python/pants/engine/internals:tls_testing',
    'src/python/pants/engine/internals/examples:fs_test',
  ],
  timeout=90,
)
