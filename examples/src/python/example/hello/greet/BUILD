# Copyright 2014 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).


# Note that the target has no explicit name, so it defaults to the name
# of the directory, in this case 'greet'.
# It also has no explicit sources, so it defaults to the sources implied
# by the target type, in this case "globs('*.py')".
python_library(
  dependencies=[
    '3rdparty/python:ansicolors',
  ],
)


compile_cython(
  name='compile-plugins',
  sources=['setup.py', 'example.cpp'],
  output='wrappers.cpython-36m-x86_64-linux-gnu.so',
  dependencies=[
    '3rdparty/python:cython'
  ]
)

python_library(
  name='example',
  sources=['example/**/*.py', '!example/files/**/*.py'],
  dependencies=[
    ':compile-plugins',
  ]
)
