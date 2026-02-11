#!/usr/bin/env python3
"""Find cycles in a dependency graph from `pants peek` output.

Usage:
    pants peek :: > peek_output.json
    python find_cycles.py peek_output.json
"""

import argparse
import json
import sys
from collections import defaultdict


def build_graph(peek_output: list[dict]) -> dict[str, list[str]]:
    """Build adjacency list from peek output."""
    graph = defaultdict(list)
    for target in peek_output:
        address = target.get("address", "")
        deps = target.get("dependencies", []) or []
        graph[address] = list(deps)
        # Ensure all dependencies are in the graph even if not in peek output
        for dep in deps:
            if dep not in graph:
                graph[dep] = []
    return dict(graph)


def find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Find all cycles in the graph using DFS."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    parent = {}
    cycles = []

    def dfs(node: str, path: list[str]) -> None:
        color[node] = GRAY
        for neighbor in graph.get(node, []):
            if neighbor not in color:
                # Node not in graph keys, skip
                continue
            if color[neighbor] == GRAY:
                # Found a cycle - extract it
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)
            elif color[neighbor] == WHITE:
                parent[neighbor] = node
                dfs(neighbor, path + [neighbor])
        color[node] = BLACK

    for node in graph:
        if color[node] == WHITE:
            dfs(node, [node])

    return cycles


def normalize_cycle(cycle: list[str]) -> tuple[str, ...]:
    """Normalize a cycle to start from the lexicographically smallest element."""
    if len(cycle) <= 1:
        return tuple(cycle)
    # Remove the duplicate last element
    cycle = cycle[:-1]
    # Find the smallest element and rotate
    min_idx = cycle.index(min(cycle))
    rotated = cycle[min_idx:] + cycle[:min_idx]
    return tuple(rotated)


def deduplicate_cycles(cycles: list[list[str]]) -> list[list[str]]:
    """Remove duplicate cycles (same cycle starting from different nodes)."""
    seen = set()
    unique = []
    for cycle in cycles:
        normalized = normalize_cycle(cycle)
        if normalized not in seen:
            seen.add(normalized)
            unique.append(list(normalized) + [normalized[0]])
    return unique


def get_directory_at_depth(address: str, depth: int) -> str:
    """Extract the directory at a specific depth from the repo root.

    Examples (depth=2):
        src/python/pants/util/strutil.py -> src/python
        src/python/pants/util:strutil -> src/python
        3rdparty/python#ansicolors -> 3rdparty/python

    Examples (depth=3):
        src/python/pants/util/strutil.py -> src/python/pants
        src/python/pants/util:strutil -> src/python/pants
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


def spans_multiple_directories_at_depth(cycle: list[str], depth: int) -> bool:
    """Check if a cycle spans more than one directory at the given depth."""
    # Exclude the duplicate last element
    targets = cycle[:-1] if len(cycle) > 1 else cycle
    directories = {get_directory_at_depth(target, depth) for target in targets}
    return len(directories) > 1


def main():
    parser = argparse.ArgumentParser(
        description="Find cycles in a dependency graph from `pants peek` output."
    )
    parser.add_argument("file", help="JSON file containing `pants peek` output")
    parser.add_argument(
        "--cycle-depth",
        type=int,
        metavar="N",
        help="Only show cycles that span multiple directories at depth N from repo root",
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

    graph = build_graph(data)
    print(f"Analyzed {len(graph)} targets", file=sys.stderr)

    cycles = find_cycles(graph)
    unique_cycles = deduplicate_cycles(cycles)

    if args.cycle_depth is not None:
        unique_cycles = [
            c for c in unique_cycles
            if spans_multiple_directories_at_depth(c, args.cycle_depth)
        ]

    if not unique_cycles:
        print("No cycles found!")
        sys.exit(0)

    print(f"Found {len(unique_cycles)} cycle(s):\n")
    for i, cycle in enumerate(unique_cycles, 1):
        print(f"Cycle {i} ({len(cycle) - 1} targets):")
        print("  " + " ->\n  ".join(cycle))
        print()

    sys.exit(1)


if __name__ == "__main__":
    main()
