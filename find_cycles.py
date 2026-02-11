#!/usr/bin/env python3
"""Find cycles in a dependency graph from `pants peek` output.

Usage:
    pants peek :: > peek_output.json
    python find_cycles.py peek_output.json
"""

import argparse
import fnmatch
import json
import sys
from collections import defaultdict


def matches_pattern(address: str, pattern: str) -> bool:
    """Check if an address matches a glob pattern.

    If the pattern contains no '/', it's matched against just the filename portion.
    Otherwise, it's matched against the full address.
    """
    if "/" not in pattern:
        # Match against just the filename/target portion
        # Handle : separator (e.g., src/foo:bar -> bar)
        if ":" in address:
            name = address.rsplit(":", 1)[1]
        # Handle # separator (e.g., 3rdparty/python#ansicolors -> ansicolors)
        elif "#" in address:
            name = address.split("#")[1]
        else:
            # Use the last path component
            name = address.rsplit("/", 1)[-1]
        return fnmatch.fnmatch(name, pattern)
    else:
        return fnmatch.fnmatch(address, pattern)


def matches_globs(
    address: str,
    include_globs: list[str] | None,
    exclude_globs: list[str] | None,
) -> bool:
    """Check if an address matches the include/exclude glob patterns.

    Returns True if:
    - No include_globs specified, or address matches at least one include glob
    - AND address does not match any exclude glob
    """
    # Check exclusions first
    if exclude_globs:
        for pattern in exclude_globs:
            if matches_pattern(address, pattern):
                return False

    # Check inclusions
    if include_globs:
        for pattern in include_globs:
            if matches_pattern(address, pattern):
                return True
        return False

    return True


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


def build_coarse_graph(
    graph: dict[str, list[str]], depth: int
) -> tuple[dict[str, list[str]], dict[tuple[str, str], list[tuple[str, str]]]]:
    """Build a coarsened graph where nodes are directories at the given depth.

    Returns:
        - coarse_graph: directory -> list of directories it depends on
        - edge_mapping: (coarse_src, coarse_dst) -> list of (fine_src, fine_dst) edges
    """
    coarse_graph: dict[str, set[str]] = defaultdict(set)
    edge_mapping: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)

    for node, deps in graph.items():
        coarse_node = get_directory_at_depth(node, depth)
        for dep in deps:
            coarse_dep = get_directory_at_depth(dep, depth)
            if coarse_node != coarse_dep:  # Skip self-loops at coarse level
                coarse_graph[coarse_node].add(coarse_dep)
                edge_mapping[(coarse_node, coarse_dep)].append((node, dep))
        # Ensure node exists in graph even with no cross-directory deps
        if coarse_node not in coarse_graph:
            coarse_graph[coarse_node] = set()

    # Convert sets to lists for compatibility with find_cycles
    return {k: list(v) for k, v in coarse_graph.items()}, dict(edge_mapping)


def find_sccs(graph: dict[str, list[str]]) -> list[list[str]]:
    """Find strongly connected components using Tarjan's algorithm.

    Returns a list of SCCs, where each SCC is a list of nodes.
    SCCs with more than one node contain cycles.
    """
    index_counter = [0]
    stack: list[str] = []
    lowlinks: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def strongconnect(node: str) -> None:
        index[node] = index_counter[0]
        lowlinks[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True

        for neighbor in graph.get(node, []):
            if neighbor not in index:
                strongconnect(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif on_stack.get(neighbor, False):
                lowlinks[node] = min(lowlinks[node], index[neighbor])

        if lowlinks[node] == index[node]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == node:
                    break
            sccs.append(scc)

    for node in graph:
        if node not in index:
            strongconnect(node)

    return sccs


def find_minimum_cuts(cycles: list[list[str]]) -> list[tuple[tuple[str, str], int]]:
    """Find a small set of edges to remove to eliminate all cycles.

    Uses a greedy approach: repeatedly remove the edge that appears in the most cycles.
    This is not guaranteed to be optimal but is a good approximation.

    Returns a list of (edge, count) tuples, where count is the number of cycles
    the edge appears in (across all input cycles, not just remaining ones).
    """
    if not cycles:
        return []

    # Convert cycles to sets of edges for faster lookup
    cycle_edges: list[set[tuple[str, str]]] = []
    for cycle in cycles:
        edges: set[tuple[str, str]] = set()
        for i in range(len(cycle) - 1):
            edges.add((cycle[i], cycle[i + 1]))
        cycle_edges.append(edges)

    # Precompute total count for each edge across all cycles
    total_edge_counts: dict[tuple[str, str], int] = defaultdict(int)
    for edges in cycle_edges:
        for edge in edges:
            total_edge_counts[edge] += 1

    cuts: list[tuple[tuple[str, str], int]] = []
    remaining_cycles = list(range(len(cycle_edges)))

    while remaining_cycles:
        # Count how many remaining cycles each edge appears in
        edge_counts: dict[tuple[str, str], int] = defaultdict(int)
        for idx in remaining_cycles:
            for edge in cycle_edges[idx]:
                edge_counts[edge] += 1

        # Pick the edge that appears in the most cycles
        best_edge = max(edge_counts.keys(), key=lambda e: edge_counts[e])
        cuts.append((best_edge, total_edge_counts[best_edge]))

        # Remove cycles that contain this edge
        remaining_cycles = [
            idx for idx in remaining_cycles
            if best_edge not in cycle_edges[idx]
        ]

    # Sort by count descending
    cuts.sort(key=lambda x: x[1], reverse=True)

    return cuts


def main():
    parser = argparse.ArgumentParser(
        description="Find cycles in a dependency graph from `pants peek` output."
    )
    parser.add_argument("file", help="JSON file containing `pants peek` output")
    parser.add_argument(
        "--cycle-depth",
        type=int,
        metavar="N",
        help="Coarsen cycles to directories at depth N, group fine-grained cycles by coarse cycle",
    )
    parser.add_argument(
        "--include-globs",
        nargs="+",
        metavar="PATTERN",
        help="Only include targets whose addresses match these glob patterns (e.g., 'src/python/**')",
    )
    parser.add_argument(
        "--exclude-globs",
        nargs="+",
        metavar="PATTERN",
        help="Exclude targets whose addresses match these glob patterns",
    )
    parser.add_argument(
        "--glob-mode",
        choices=["any", "all"],
        default="all",
        help="'all' (default): every node in a cycle must match the include globs. "
             "'any': report cycles where at least one node matches.",
    )
    parser.add_argument(
        "--show-cuts",
        action="store_true",
        help="Show the minimum set of edges to remove to eliminate all cycles.",
    )
    parser.add_argument(
        "--find-sccs",
        action="store_true",
        help="Find strongly connected components (the maximum grouping where the induced graph is acyclic).",
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

    has_globs = args.include_globs or args.exclude_globs

    if has_globs and args.glob_mode == "all":
        original_count = len(data)
        data = [
            t for t in data
            if matches_globs(t.get("address", ""), args.include_globs, args.exclude_globs)
        ]
        print(f"Filtered to {len(data)}/{original_count} targets matching globs", file=sys.stderr)

    graph = build_graph(data)

    if has_globs and args.glob_mode == "all":
        # Filter graph to only include nodes and edges matching the globs
        graph = {
            node: [
                dep for dep in deps
                if matches_globs(dep, args.include_globs, args.exclude_globs)
            ]
            for node, deps in graph.items()
            if matches_globs(node, args.include_globs, args.exclude_globs)
        }
    print(f"Analyzed {len(graph)} targets", file=sys.stderr)

    if args.cycle_depth is not None:
        # Build coarsened graph and find cycles at directory level
        coarse_graph, edge_mapping = build_coarse_graph(graph, args.cycle_depth)
        print(f"Coarsened to {len(coarse_graph)} directories", file=sys.stderr)

        coarse_cycles = find_cycles(coarse_graph)
        unique_coarse_cycles = deduplicate_cycles(coarse_cycles)

        if has_globs and args.glob_mode == "any":
            # Filter to coarse cycles where at least two directories match the globs
            unique_coarse_cycles = [
                c for c in unique_coarse_cycles
                if sum(1 for node in c[:-1] if matches_globs(node, args.include_globs, args.exclude_globs)) >= 2
            ]

        if not unique_coarse_cycles:
            print("No cross-directory cycles found!")
            if not args.find_sccs:
                sys.exit(0)
        else:
            print(f"Found {len(unique_coarse_cycles)} coarse cycle(s):\n")
            for i, cycle in enumerate(sorted(unique_coarse_cycles), 1):
                print(f"Coarse Cycle {i} ({len(cycle) - 1} directories):")
                print("  " + " ->\n  ".join(cycle))

                # Collect fine-grained edges for this cycle
                fine_edges: list[tuple[str, str]] = []
                for j in range(len(cycle) - 1):
                    coarse_edge = (cycle[j], cycle[j + 1])
                    fine_edges.extend(edge_mapping.get(coarse_edge, []))

                print(f"\n  Fine-grained edges ({len(fine_edges)}):")
                for j, (src, dst) in enumerate(fine_edges, 1):
                    print(f"    {j}. {src} -> {dst}")
                print()

            if args.show_cuts:
                cuts = find_minimum_cuts(unique_coarse_cycles)
                print(f"Minimum cuts to eliminate all coarse cycles ({len(cuts)} edge(s)):\n")
                for i, ((src, dst), count) in enumerate(cuts, 1):
                    fine_edges = edge_mapping.get((src, dst), [])
                    print(f"  {i}. {src} -> {dst} (in {count} cycle(s), {len(fine_edges)} fine edge(s)):")
                    for fine_src, fine_dst in fine_edges:
                        print(f"      {fine_src} -> {fine_dst}")
                print()

        if args.find_sccs:
            sccs = find_sccs(coarse_graph)
            # Sort by size descending, then by first element for stability
            sccs.sort(key=lambda scc: (-len(scc), min(scc)))
            cyclic_sccs = [scc for scc in sccs if len(scc) > 1]
            acyclic_count = len(sccs) - len(cyclic_sccs)

            print(f"Found {len(sccs)} SCC(s) ({acyclic_count} acyclic, {len(cyclic_sccs)} with cycles):\n")
            for i, scc in enumerate(sccs, 1):
                if len(scc) == 1:
                    print(f"  {i}. {scc[0]}")
                else:
                    print(f"  {i}. ({len(scc)} directories):")
                    for node in sorted(scc):
                        print(f"      {node}")
            print()
    else:
        cycles = find_cycles(graph)
        unique_cycles = deduplicate_cycles(cycles)

        if has_globs and args.glob_mode == "any":
            # Filter to cycles where at least two distinct nodes match the globs
            unique_cycles = [
                c for c in unique_cycles
                if sum(1 for node in c[:-1] if matches_globs(node, args.include_globs, args.exclude_globs)) >= 2
            ]

        if not unique_cycles:
            print("No cycles found!")
            if not args.find_sccs:
                sys.exit(0)
        else:
            print(f"Found {len(unique_cycles)} cycle(s):\n")
            for i, cycle in enumerate(unique_cycles, 1):
                print(f"Cycle {i} ({len(cycle) - 1} targets):")
                print("  " + " ->\n  ".join(cycle))
                print()

            if args.show_cuts:
                cuts = find_minimum_cuts(unique_cycles)
                print(f"Minimum cuts to eliminate all cycles ({len(cuts)} edge(s)):\n")
                for i, ((src, dst), count) in enumerate(cuts, 1):
                    print(f"  {i}. {src} -> {dst} (in {count} cycle(s))")
                print()

        if args.find_sccs:
            sccs = find_sccs(graph)
            # Sort by size descending, then by first element for stability
            sccs.sort(key=lambda scc: (-len(scc), min(scc)))
            cyclic_sccs = [scc for scc in sccs if len(scc) > 1]
            acyclic_count = len(sccs) - len(cyclic_sccs)

            print(f"Found {len(sccs)} SCC(s) ({acyclic_count} acyclic, {len(cyclic_sccs)} with cycles):\n")
            for i, scc in enumerate(sccs, 1):
                if len(scc) == 1:
                    print(f"  {i}. {scc[0]}")
                else:
                    print(f"  {i}. ({len(scc)} targets):")
                    for node in sorted(scc):
                        print(f"      {node}")
            print()

    sys.exit(1)


if __name__ == "__main__":
    main()
