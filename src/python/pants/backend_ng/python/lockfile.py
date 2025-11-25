# Copyright 2026 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import tomllib
from collections import deque
from dataclasses import dataclass

from pants.engine.fs import CreateDigest, FileContent
from pants.engine.internals.native_engine import Digest
from pants.engine.intrinsics import create_digest, get_digest_contents
from pants.engine.rules import collect_rules, rule

_UV_LOCK_PATH = "uv.lock"


@dataclass(frozen=True)
class UvLock:
    digest: Digest


@dataclass(frozen=True)
class UvLockSubsetRequest:
    uv_lock: UvLock
    root_packages: tuple[str, ...]


async def deserialize_uv_lock(uv_lock: UvLock) -> dict:
    digest_contents = tuple(await get_digest_contents(uv_lock.digest))
    if len(digest_contents) != 1:
        raise ValueError(f"UvLock digest expected to contain exactly one file")
    file_content = digest_contents[0]
    if file_content.path != _UV_LOCK_PATH:
        raise ValueError(f"UvLock digest expected to contain {_UV_LOCK_PATH}")
    return tomllib.loads(file_content.content)


@rule
async def subset_uv_lock(req: UvLockSubsetRequest) -> UvLock:
    # Right now this isn't in use and we always run against the entire lockfile.
    # TODO: Evaluate the need for subsetting. The advantage would be caching things like
    #  test results against a smaller set of requirements. But the actual value of this is
    #  hard to measure at the moment. E.g., it may be the case that since uv locking is very fast,
    #  users regenerate locks more aggressively, with less constraint pinning, which may in turn
    #  mean that common requirements get upgraded frequently, and most/all tests get invalidated
    #  on every lockfile change anyway.
    uv_lock_data = await deserialize_uv_lock(req.uv_lock)
    name_to_pkg = {pkg["name"]: pkg for pkg in uv_lock_data.get("package", [])}
    queue = deque(root for root in req.root_packages if root in name_to_pkg)
    visited = set(queue)
    subset = []
    while queue:
        pkg_name = queue.popleft()
        pkg = name_to_pkg[pkg_name]
        subset.append(pkg)
        for dep_name in pkg.get("dependencies"):
            if dep_name not in visited and dep_name in name_to_pkg:
                visited.add(dep_name)
                queue.append(dep_name)

    # Modify the package field, but keep the other fields the same.
    uv_lock_data["package"] = subset
    serialized_uv_lock_data = tomllib.dumps(uv_lock_data)
    new_digest = await create_digest(
        CreateDigest(
            [FileContent(path=_UV_LOCK_PATH, content=serialized_uv_lock_data, is_executable=False)]
        )
    )
    return UvLock(new_digest)


@rule
async def sync_uv_lock() -> UvLock:
    pass


def rules():
    return [*collect_rules()]
