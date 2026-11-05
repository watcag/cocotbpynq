"""
Generates pblock constraints (XDC) that partition the reconfigurable area
across N reconfigurable partitions.

Each partition gets a connected set of clock regions. The algorithm finds a
Hamiltonian path through the adjacency graph of reconfigurable regions
(two regions are adjacent if they differ by 1 in X or Y), then splits that
path into N balanced groups. Because consecutive path nodes are physically
adjacent, every group is guaranteed connected.

Backtracking with Warnsdorff's heuristic finds the path. For typical FPGA
region sets (<20 nodes) this completes in microseconds.
"""

from pathlib import Path


def _build_adjacency(regions):
    """Build adjacency dict. Two clock regions are adjacent if Manhattan distance = 1."""
    def parse(r):
        x, y = r[1:].split("Y")
        return int(x), int(y)

    coords = {r: parse(r) for r in regions}
    region_set = set(regions)
    adj = {r: [] for r in regions}

    for r, (x, y) in coords.items():
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nb = f"X{x+dx}Y{y+dy}"
            if nb in region_set:
                adj[r].append(nb)

    return adj, coords


def _is_connected(regions, adj):
    """Check if all regions form a connected graph."""
    if not regions:
        return True
    visited = set()
    stack = [regions[0]]
    visited.add(regions[0])
    while stack:
        node = stack.pop()
        for nb in adj[node]:
            if nb not in visited:
                visited.add(nb)
                stack.append(nb)
    return len(visited) == len(regions)


def _find_hamiltonian_path(regions, adj):
    """Find a path visiting all regions where consecutive entries are adjacent.

    Uses backtracking with Warnsdorff's heuristic (visit the neighbor with
    the fewest remaining unvisited neighbors first). Starts from low-degree
    nodes (corners/endpoints) since Hamiltonian paths must start/end at
    degree-1 nodes when they exist.
    """
    n = len(regions)
    if n <= 1:
        return list(regions)

    starts = sorted(regions, key=lambda r: len(adj[r]))

    def backtrack(path, visited):
        if len(path) == n:
            return path[:]
        current = path[-1]
        neighbors = sorted(
            (nb for nb in adj[current] if nb not in visited),
            key=lambda nb: sum(1 for x in adj[nb] if x not in visited),
        )
        for nb in neighbors:
            visited.add(nb)
            path.append(nb)
            result = backtrack(path, visited)
            if result:
                return result
            path.pop()
            visited.remove(nb)
        return None

    for start in starts:
        result = backtrack([start], {start})
        if result:
            return result
    return None


def _layout_groups(board, n):
    """Clock-region groups from the board's explicit layout for n partitions.

    Boards whose clock regions differ in kind (e.g. Versal, where DSPs and NoC
    endpoints sit in different columns) list their layouts instead of leaving
    the split to the resource-blind path algorithm.
    """
    layouts = board["layouts"]
    if n not in layouts:
        raise ValueError(
            f"Requested {n} partitions but the board has layouts for "
            f"{sorted(layouts)} partitions"
        )
    groups = [list(g) for g in layouts[n]]
    for group in groups:
        adj, _ = _build_adjacency(group)
        if not _is_connected(group, adj):
            raise ValueError(f"Layout group {group} is not a connected set of clock regions")
    return groups


def partition_groups(board, n):
    """The clock regions of each of n partitions: the board's layout, or a split of its path."""
    if "layouts" in board:
        return _layout_groups(board, n)
    if n <= 2 and "reconfigurable_regions_lte2" in board:
        regions = list(board["reconfigurable_regions_lte2"])
    else:
        regions = list(board["reconfigurable_regions"])

    if n > len(regions):
        raise ValueError(
            f"Requested {n} partitions but board only has "
            f"{len(regions)} reconfigurable clock regions"
        )

    adj, coords = _build_adjacency(regions)

    if not _is_connected(regions, adj):
        raise ValueError(
            "Reconfigurable regions do not form a connected graph. "
            "Every region must be reachable from every other region "
            "via adjacent clock regions."
        )

    path = _find_hamiltonian_path(regions, adj)
    if path is None:
        raise ValueError(
            "Cannot find a Hamiltonian path through the reconfigurable "
            "regions. The region topology does not allow a linear ordering "
            "where every consecutive pair is adjacent. Consider adjusting "
            "reconfigurable_regions in boards.py to form a simpler shape "
            "(e.g., avoid T-junctions)."
        )

    base = len(path) // n
    extra = len(path) % n
    groups = []
    idx = 0
    for i in range(n):
        count = base + (1 if i < extra else 0)
        groups.append(path[idx:idx + count])
        idx += count
    return groups


def generate_pblocks_xdc(board, partitions, design_name, noc=False):
    """noc: the partitions hold their NoC input (an NSU), so their pblocks take the NSU sites."""
    groups = partition_groups(board, len(partitions))
    return _pblocks_xdc(board, partitions, groups, design_name, noc)


def _pblocks_xdc(board, partitions, groups, design_name, noc=False):
    lines = []
    for i, part in enumerate(partitions):
        pname = part["partition_name"]
        cr_list = " ".join(groups[i])

        lines.append(f"create_pblock pblock_{pname}")
        lines.append(
            f"add_cells_to_pblock [get_pblocks pblock_{pname}] "
            f"[get_cells -quiet [list {design_name}_i/{pname}/rp]]"
        )
        for res in board["pblock_resources"] + (["NOC_NSU512"] if noc else []):
            lines.append(
                f"resize_pblock pblock_{pname} -add "
                f"[get_sites {res}* -of [get_clock_regions {{{cr_list}}}]]"
            )
        if board["family"] != "versal":  # Versal resets reconfigured logic itself (DRC HDPR-32)
            lines.append(f"set_property RESET_AFTER_RECONFIG true [get_pblocks pblock_{pname}]")
        lines.append(f"set_property SNAPPING_MODE ON [get_pblocks pblock_{pname}]")
        lines.append("")

    return "\n".join(lines)


def write_pblocks_xdc(board, partitions, design_name, output_dir, noc=False):
    xdc_content = generate_pblocks_xdc(board, partitions, design_name, noc)
    xdc_path = Path(output_dir) / "pblocks.xdc"
    xdc_path.write_text(xdc_content)
    return xdc_path
