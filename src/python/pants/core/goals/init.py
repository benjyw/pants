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


@union
class PutativeSourceRootsRequest(metaclass=ABCMeta):
    pass


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
        for res in all_putative_source_roots:
            print("XXXX " + res.path)
        for src_root in asr:
            print_stdout(src_root.path or ".")
    return Init(0)


def rules():
    return collect_rules()
