# Copyright 2021 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from abc import ABCMeta
from dataclasses import dataclass
from typing import Iterable

from pants.engine.collection import DeduplicatedCollection
from pants.engine.console import Console
from pants.engine.goal import Goal, GoalSubsystem, LineOriented
from pants.engine.internals.selectors import Get, MultiGet
from pants.engine.rules import collect_rules, goal_rule
from pants.engine.unions import union, UnionMembership
from pants.source.source_root import AllSourceRoots
from pants.util.frozendict import FrozenDict


@union
class PutativeTargetsRequest(metaclass=ABCMeta):
    pass


@union
class PutativeSourceRootsRequest(metaclass=ABCMeta):
    pass


@dataclass(frozen=True, order=True)
class PutativeTarget:
    """A potential target to add, detected by various heuristics."""
    path: str
    name: str
    type: str
    kwargs: FrozenDict[str, str]


class PutativeTargets(DeduplicatedCollection[PutativeTarget]):
    sort_input = True

    @classmethod
    def merge(cls, tgts_iters: Iterable["PutativeTargets"]) -> "PutativeTargets":
        all_tgts = []
        for tgts in tgts_iters:
            all_tgts.extend(tgts)
        return cls(all_tgts)


@dataclass(frozen=True, order=True)
class PutativeSourceRoot:
    """A potential source root, detected by various heuristics."""
    # Relative path from the buildroot.  Note that a putative source root at the buildroot
    # is represented as ".".
    path: str


class PutativeSourceRoots(DeduplicatedCollection[PutativeSourceRoot]):
    sort_input = True

    @classmethod
    def merge(cls, roots_iters: Iterable["PutativeSourceRoots"]) -> "PutativeSourceRoots":
        all_roots = set()
        for roots in roots_iters:
            all_roots.update(roots)
        return cls(all_roots)


class InitSubsystem(LineOriented, GoalSubsystem):
    name = "init"
    help = (
        "Generate config for working with Pants."
    )


class Init(Goal):
    subsystem_cls = InitSubsystem


@goal_rule
async def init(
    init_subsystem: InitSubsystem,
    asr: AllSourceRoots,
    console: Console,
    union_membership: UnionMembership,
) -> Init:
    putative_target_request_types = union_membership[PutativeTargetsRequest]
    putative_target_reqs = [req_type() for req_type in putative_target_request_types]
    putative_targets_results = await MultiGet(
        Get(PutativeTargets, PutativeTargetsRequest, req)
        for req in putative_target_reqs
    )
    all_putative_targets = PutativeTargets.merge(putative_targets_results)

    putative_source_root_request_types = union_membership[PutativeSourceRootsRequest]
    putative_source_root_reqs = [
        req_type()
        for req_type in putative_source_root_request_types
    ]
    putative_source_root_results = await MultiGet(
        Get(PutativeSourceRoots, PutativeSourceRootsRequest, req)
        for req in putative_source_root_reqs
    )
    all_putative_source_roots = PutativeSourceRoots.merge(putative_source_root_results)

    with init_subsystem.line_oriented(console) as print_stdout:
        for ptgt in all_putative_targets:
            print_stdout(f"TARGET: {ptgt.path}:{ptgt.name}")

        for res in all_putative_source_roots:
            print_stdout("XXXX " + res.path)
        for src_root in asr:
            print_stdout(src_root.path or ".")
    return Init(0)


def rules():
    return collect_rules()
