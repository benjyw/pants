# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).


import os
import subprocess

from pex.interpreter import PythonInterpreter
from pex.pex_builder import PEXBuilder
from pex.pex_info import PexInfo

from pants.backend.python.targets.python_library import PythonLibrary
from pants.backend.python.tasks.resolve_requirements import ResolveRequirements
from pants.base.build_environment import get_buildroot
from pants.base.exceptions import TaskError
from pants.base.payload import Payload
from pants.base.payload_field import PrimitiveField
from pants.build_graph.resources import Resources
from pants.python.pex_build_util import PexBuilderWrapper
from pants.task.simple_codegen_task import SimpleCodegenTask
from pants.util.contextutil import temporary_dir


class CompileCython(PythonLibrary):
    def __init__(self, payload=None, address=None, output=None, **kwargs):
        payload = payload or Payload()
        payload.add_field('output', PrimitiveField(output))
        super(CompileCython, self).__init__(payload=payload, address=address, **kwargs)

    @property
    def output(self):
        return self.payload.output


class CompileCythonCreate(SimpleCodegenTask):

    gentarget_type = CompileCython

    sources_globs = tuple()

    @classmethod
    def prepare(cls, options, round_manager):
        round_manager.require_data(PythonInterpreter)
        round_manager.require_data(ResolveRequirements.REQUIREMENTS_PEX)

    @classmethod
    def product_types(cls):
        return []

    @property
    def cache_target_dirs(self):
        return True

    def execute_codegen(self, target, results_dir):
        self.context.log.info("Processing target {}".format(target))

        self._add_output_to_sources_globs(target)

        requirements_pex = self.context.products.get_data(ResolveRequirements.REQUIREMENTS_PEX)

        interpreter = self.context.products.get_data(PythonInterpreter)
        pex_info = PexInfo.default(interpreter)
        pex_info.pex_path = requirements_pex.path()
        with temporary_dir() as source_pex_chroot:
            sources_pex_builder = PEXBuilder(
                path=source_pex_chroot,
                interpreter=interpreter,
                copy=True,
                pex_info=pex_info
            )
            builder_wrapper = PexBuilderWrapper.Factory.create(builder=sources_pex_builder)
            builder_wrapper.add_sources_from(target)
            builder_wrapper.freeze()

            setup_py_paths = []
            for source in target.sources_relative_to_source_root():
                if os.path.basename(source) == 'setup.py':
                    setup_py_paths.append(source)
            if len(setup_py_paths) != 1:
                raise TaskError(
                    'Expected target {} to own exactly one setup.py, found {}'.format(
                        setup_py_paths,
                        len(setup_py_paths)
                    )
                )
            setup_py_path = setup_py_paths[0]

            full_path = os.path.join(get_buildroot(), target.target_base)
            cythonize = [interpreter.binary, os.path.join(full_path, setup_py_path), 'build_ext', '--inplace', '--verbose']
            self.context.log.info('cython wrapper setup.py command will be: {}'.format(cythonize))

            # build the C++ plugins
            subprocess.check_call(['cmake', full_path], cwd=results_dir)
            subprocess.check_call(['make'], cwd=results_dir)

            # build the cython wrappers around C++ above
            subprocess.check_call(cythonize, cwd=results_dir)

    def synthetic_target_type(self, target):
        return Resources

    @property
    def validate_sources_present(self):
        # We don't actually have sources in this package that we want to copy. We just use the sources to compile the so
        return False

    @property
    def _copy_target_attributes(self):
        return []

    @classmethod
    def _add_output_to_sources_globs(cls, target):
        cls.sources_globs = (target.output,)
