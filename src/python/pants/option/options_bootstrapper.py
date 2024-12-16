# Copyright 2014 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import itertools
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence, Tuple

from pants.base.build_environment import get_buildroot, get_default_pants_config_file, pants_version
from pants.base.exceptions import BuildConfigurationError
from pants.engine.unions import UnionMembership
from pants.option.config import Config, ConfigSource
from pants.option.custom_types import ListValueComponent
from pants.option.global_options import BootstrapOptions, GlobalOptions
from pants.option.option_types import collect_options_info, OptionInfo
from pants.option.option_value_container import OptionValueContainer
from pants.option.options import Options
from pants.option.registrar import OptionRegistrar
from pants.option.scope import GLOBAL_SCOPE, ScopeInfo
from pants.option.subsystem import Subsystem
from pants.util.dirutil import read_file
from pants.util.memo import memoized_method, memoized_property
from pants.util.ordered_set import FrozenOrderedSet
from pants.util.strutil import ensure_text, softwrap

if TYPE_CHECKING:
    from pants.build_graph.build_configuration import BuildConfiguration


@dataclass(frozen=True)
class OptionsBootstrapper:
    """Holds the result of the first stage of options parsing, and assists with parsing full
    options."""

    env_tuples: tuple[tuple[str, str], ...]
    args: tuple[str, ...]
    config_sources: tuple[ConfigSource]
    allow_pantsrc: bool

    def __repr__(self) -> str:
        env = {pair[0]: pair[1] for pair in self.env_tuples}
        # Bootstrap args are included in `args`. We also drop the first argument, which is the path
        # to `pants_loader.py`.
        args = list(self.args[1:])
        return f"OptionsBootstrapper(args={args}, env={env}, config={','.join(c.path for c in self.config_sources)})"

    @classmethod
    def create(
        cls, env: Mapping[str, str], args: Sequence[str], *, allow_pantsrc: bool
    ) -> OptionsBootstrapper:
        """Parses the minimum amount of configuration necessary to create an OptionsBootstrapper.

        :param env: An environment dictionary.
        :param args: An args array.
        :param allow_pantsrc: True to allow pantsrc files to be used. Unless tests are expecting to
          consume pantsrc files, they should pass False in order to avoid reading files from
          absolute paths. Production use-cases should pass True to allow options values to make the
          decision of whether to respect pantsrc files.
        """
        args = tuple(args)
        bootstrap_options = cls._create_bootstrap_options(args, env, allow_pantsrc)
        with warnings.catch_warnings(record=True):
            # We need to set this env var to allow various static help strings to reference the
            # right name (via `pants.util.docutil`), and we need to do it as early as possible to
            # avoid needing to lazily import code to avoid chicken-and-egg-problems. This is the
            # earliest place it makes sense to do so and is generically used by both the local and
            # remote pants runners.
            os.environ["__PANTS_BIN_NAME"] = munge_bin_name(
                bootstrap_options.for_global_scope().pants_bin_name, get_buildroot()
            )

            # TODO: We really only need the env vars starting with PANTS_, plus any env
            #  vars used in env.FOO-style interpolation in config files.
            #  Filtering to just those would allow OptionsBootstrapper to have a less
            #  unwieldy __str__.
            #  We used to filter all but PANTS_* (https://github.com/pantsbuild/pants/pull/7312),
            #  but we can't now because of env interpolation in the native config file parser.
            #  We can revisit this once the legacy python parser is no more, and we refactor
            #  the OptionsBootstrapper and/or convert it to Rust.
            env_tuples = tuple(sorted(env.items()))
            return cls(
                env_tuples=env_tuples,
                args=args,
                config_sources=tuple(),
                allow_pantsrc=allow_pantsrc,
            )

    @memoized_property
    def env(self) -> dict[str, str]:
        return dict(self.env_tuples)

    @staticmethod
    def _create_bootstrap_options(args: Sequence[str], env: dict[str, str], allow_pantsrc: bool) -> Options:
        """Create an Options instance containing just the bootstrap options.

        These are the options needed to create a scheduler.
        """
        bootstrap_options_registrar = OptionRegistrar(GLOBAL_SCOPE)
        for option_info in collect_options_info(BootstrapOptions):
            bootstrap_options_registrar.register(*option_info.args, **option_info.kwargs)

        return Options.create(
            env,
            [],
            [GlobalOptions.get_scope_info()],
            args=args,
            bootstrap_option_info=bootstrap_options_registrar.option_registrations_iter(),
            allow_unknown_options=True,
            allow_pantsrc=allow_pantsrc,
        )

    @memoized_property
    def bootstrap_options(self) -> Options:
        """An Options instance containing just the bootstrap options.

        These are the options needed to create a scheduler.
        """
        return self._create_bootstrap_options(self.args, self.env, self.allow_pantsrc)

    @memoized_method
    def _full_options(
        self,
        known_scope_infos: FrozenOrderedSet[ScopeInfo],
        union_membership: UnionMembership,
        allow_unknown_options: bool = False,
    ) -> Options:
        bootstrap_options_registrar = OptionRegistrar(GLOBAL_SCOPE)
        for option_info in collect_options_info(BootstrapOptions):
            bootstrap_options_registrar.register(*option_info.args, **option_info.kwargs)

        options = Options.create(
            self.env,
            [],
            known_scope_infos,
            args=self.args,
            bootstrap_option_info=bootstrap_options_registrar.option_registrations_iter(),
            allow_unknown_options=allow_unknown_options,
            allow_pantsrc=self.allow_pantsrc,
        )

        distinct_subsystem_classes: set[type[Subsystem]] = set()
        for ksi in known_scope_infos:
            if not ksi.subsystem_cls or ksi.subsystem_cls in distinct_subsystem_classes:
                continue
            distinct_subsystem_classes.add(ksi.subsystem_cls)
            ksi.subsystem_cls.register_options_on_scope(options, union_membership)

        return options

    def full_options_for_scopes(
        self,
        known_scope_infos: Iterable[ScopeInfo],
        union_membership: UnionMembership,
        allow_unknown_options: bool = False,
    ) -> Options:
        """Get the full Options instance bootstrapped by this object for the given known scopes.

        :param known_scope_infos: ScopeInfos for all scopes that may be encountered.
        :returns: A bootstrapped Options instance that also carries options for all the supplied known
                  scopes.
        """
        return self._full_options(
            FrozenOrderedSet(sorted(known_scope_infos, key=lambda si: si.scope)),
            union_membership,
            allow_unknown_options=allow_unknown_options,
        )

    def full_options(
        self, build_configuration: BuildConfiguration, union_membership: UnionMembership
    ) -> Options:
        # Parse and register options.
        known_scope_infos = [
            subsystem.get_scope_info() for subsystem in build_configuration.all_subsystems
        ]
        options = self.full_options_for_scopes(
            known_scope_infos,
            union_membership,
            allow_unknown_options=build_configuration.allow_unknown_options,
        )

        global_options = options.for_global_scope()
        if global_options.pants_version != pants_version():
            raise BuildConfigurationError(
                softwrap(
                    f"""
                        Version mismatch: Requested version was {global_options.pants_version},
                        our version is {pants_version()}.
                        """
                )
            )
        GlobalOptions.validate_instance(options.for_global_scope())
        return options


def munge_bin_name(pants_bin_name: str, build_root: str) -> str:
    # Determine a useful bin name to embed in help strings.
    # The bin name gets embedded in help comments in generated lockfiles,
    # so we never want to use an abspath.
    if os.path.isabs(pants_bin_name):
        pants_bin_name = os.path.realpath(pants_bin_name)
        build_root = os.path.realpath(os.path.abspath(build_root))
        # If it's in the buildroot, use the relpath from there. Otherwise use the basename.
        pants_bin_relpath = os.path.relpath(pants_bin_name, build_root)
        if pants_bin_relpath.startswith(".."):
            pants_bin_name = os.path.basename(pants_bin_name)
        else:
            pants_bin_name = os.path.join(".", pants_bin_relpath)
    return pants_bin_name
