#!/usr/bin/env python3
"""Coarsen a dependency graph from `pants peek` output.

Merges all nodes at a given depth from the repo root into a single coarse node.
Dependencies between original nodes become dependencies between coarse nodes.
Self-dependencies are dropped.

Usage:
    pants peek :: > peek_output.json
    python coarsen_graph.py --depth 2 peek_output.json
"""

import argparse
import json
import sys
from collections import defaultdict


def get_coarse_node(address: str, depth: int) -> str:
    """Get the coarse node path at the given depth.

    Examples (depth=2):
        src/python/pants/util/strutil.py -> src/python
        src/python/pants/util:strutil -> src/python
        3rdparty/python#ansicolors -> 3rdparty/python
    """
    # Handle # separator (e.g., 3rdparty/python#ansicolors)
    if "#" in address:
        address = address.split("#")[0]
    # Handle : separator (e.g., src/foo:bar)
    if ":" in address:
        address = address.rsplit(":", 1)[0]
    # Handle file paths (e.g., src/foo/bar.py) - get the directory
    if "." in address.rsplit("/", 1)[-1]:
        address = address.rsplit("/", 1)[0]

    parts = address.split("/")
    return "/".join(parts[:depth])


def coarsen_graph(peek_output: list[dict], depth: int) -> list[dict]:
    """Coarsen the dependency graph to the given depth."""
    # Map from coarse node to set of coarse dependencies
    coarse_deps: dict[str, set[str]] = defaultdict(set)

    for target in peek_output:
        address = target.get("address", "")
        deps = target.get("dependencies", []) or []

        coarse_node = get_coarse_node(address, depth)
        if not coarse_node:
            continue

        for dep in deps:
            coarse_dep = get_coarse_node(dep, depth)
            # Skip self-dependencies and empty nodes
            if coarse_dep and coarse_dep != coarse_node:
                coarse_deps[coarse_node].add(coarse_dep)

        # Ensure the node exists even if it has no external dependencies
        if coarse_node not in coarse_deps:
            coarse_deps[coarse_node] = set()

    # Convert to output format
    result = []
    for address in sorted(coarse_deps.keys()):
        result.append({
            "address": address,
            "dependencies": sorted(coarse_deps[address])
        })

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Coarsen a dependency graph from `pants peek` output."
    )
    parser.add_argument("file", help="JSON file containing `pants peek` output")
    parser.add_argument(
        "--depth",
        type=int,
        required=True,
        metavar="N",
        help="Depth from repo root at which to coarsen nodes",
    )
    args = parser.parse_args()

    try:
        with open(args.file) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {args.file}: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        print("Error: Expected a JSON array from `pants peek`", file=sys.stderr)
        sys.exit(1)

    coarsened = coarsen_graph(data, args.depth)

    print(f"Coarsened {len(data)} targets into {len(coarsened)} nodes at depth {args.depth}", file=sys.stderr)

    print(json.dumps(coarsened, indent=2))


if __name__ == "__main__":
    main()
