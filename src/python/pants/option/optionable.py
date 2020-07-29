# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import functools
import inspect
from abc import ABC, abstractmethod
from typing import Type

from pants.engine.internals.selectors import Get, GetConstraints
from pants.option.scope import Scope, ScopedOptions


async def _construct_optionable(optionable_factory):
    scope = optionable_factory.options_scope
    scoped_options = await Get(ScopedOptions, Scope(str(scope)))
    return optionable_factory.optionable_cls(scope, scoped_options.options)


class OptionableFactory(ABC):
    """A mixin that provides a method that returns an @rule to construct subclasses of Optionable.

    Optionable subclasses constructed in this manner must have a particular constructor shape, which
    is loosely defined by `_construct_optionable` and `OptionableFactory.signature`.
    """

    @property
    @abstractmethod
    def optionable_cls(self) -> Type["Optionable"]:
        """The Optionable class that is constructed by this OptionableFactory."""

    @property
    @abstractmethod
    def options_scope(self):
        """The scope from which the ScopedOptions for the target Optionable will be parsed."""

    @classmethod
    def signature(cls):
        """Returns kwargs to construct a `TaskRule` that will construct the target Optionable.

        TODO: This indirection avoids a cycle between this module and the `rules` module.
        """
        partial_construct_optionable = functools.partial(_construct_optionable, cls)

        # NB: We must populate several dunder methods on the partial function because partial
        # functions do not have these defined by default and the engine uses these values to
        # visualize functions in error messages and the rule graph.
        snake_scope = cls.options_scope.replace("-", "_")
        name = f"construct_scope_{snake_scope}"
        partial_construct_optionable.__name__ = name
        partial_construct_optionable.__module__ = cls.__module__
        _, class_definition_lineno = inspect.getsourcelines(cls)
        partial_construct_optionable.__line_number__ = class_definition_lineno

        return dict(
            output_type=cls.optionable_cls,
            input_selectors=(),
            func=partial_construct_optionable,
            input_gets=(GetConstraints(product_type=ScopedOptions, subject_declared_type=Scope),),
            canonical_name=name,
        )
