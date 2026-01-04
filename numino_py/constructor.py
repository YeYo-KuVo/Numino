from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Set
import random
from collections import deque

from solver import Puzzle, Coord, Val
from bias import choose_block_sizes_biased


@dataclass
class ConstructConfig:
    rows: int
    cols: int
    palette: List[str]          # e.g. ["R","Y","B"]
    numbers: List[int]          # e.g. [1,2,3,4,5]
    seed: int

    # NEW: Bias mode (matches your UI)
    style: str = "BALANCED"     # SMALL | BALANCED | BIG | UNIFORM

    require_all_numbers: bool = True
    require_all_colors: bool = True

    max_attempts: int = 300     # restarts for partition+color


def _neighbors4(r: int, c: int, R: int, C: int) -> List[Coord]:
    out: List[Coord] = []
    if r > 0: out.append((r - 1, c))
    if r + 1 < R: out.append((r + 1, c))
    if c > 0: out.append((r, c - 1))
    if c + 1 < C: out.append((r, c + 1))
    return out


def _area_feasible(rows: int, cols: int, required_numbers: Sequence[int]) -> bool:
    # If you require at least one block of each number, you need at least sum(numbers) cells.
    return rows * cols >= sum(required_numbers)


def _find_all_shapes(
    start: Coord,
    size: int,
    free_cells: Set[Coord],
    R: int,
    C: int,
    limit: int,
    rng: random.Random
) -> List[List[Coord]]:
    """
    Generate up to `limit` connected shapes of `size` starting at `start`,
    using randomized compact growth.
    """
    shapes: List[List[Coord]] = []

    for _ in range(limit):
        shape = [start]
        used = {start}

        while len(shape) < size:
            cand: List[Coord] = []
            seen = set()

            for (r, c) in shape:
                for nb in _neighbors4(r, c, R, C):
                    if nb in seen:
                        continue
                    seen.add(nb)
                    if nb in free_cells and nb not in used:
                        cand.append(nb)

            if not cand:
                break

            # compactness bias: prefer cells that touch current shape more
            def score(cell: Coord) -> int:
                rr, cc = cell
                s = 0
                for nb in _neighbors4(rr, cc, R, C):
                    if nb in used:
                        s += 1
                return s

            cand.sort(key=score, reverse=True)
            pick = cand[0] if rng.random() < 0.70 else rng.choice(cand)

            used.add(pick)
            shape.append(pick)

        if len(shape) == size:
            shapes.append(shape)

    return shapes


def _partition_into_blocks(
    rng: random.Random,
    R: int,
    C: int,
    block_sizes: List[int]
) -> Optional[Tuple[Dict[Coord, int], Dict[int, int]]]:
    """
    Partition the grid into connected blocks with specified sizes.
    Returns:
      - cell_to_block: (r,c) -> block_id
      - block_size: block_id -> size
    """
    all_cells: Set[Coord] = {(r, c) for r in range(R) for c in range(C)}
    cell_to_block: Dict[Coord, int] = {}
    block_size: Dict[int, int] = {}

    # Place larger blocks first (usually easier)
    sizes = sorted(block_sizes, reverse=True)

    def next_free_cell() -> Optional[Coord]:
        for r in range(R):
            for c in range(C):
                rc = (r, c)
                if rc not in cell_to_block:
                    return rc
        return None

    def dfs(i: int) -> bool:
        if i == len(sizes):
            return True

        free = all_cells - set(cell_to_block.keys())
        start = next_free_cell()
        if start is None:
            return False

        size = sizes[i]
        if size > len(free):
            return False

        shapes = _find_all_shapes(start, size, free, R, C, limit=80, rng=rng)
        if not shapes:
            return False

        rng.shuffle(shapes)

        for shape in shapes:
            block_id = i
            for rc in shape:
                cell_to_block[rc] = block_id
            block_size[block_id] = size

            if dfs(i + 1):
                return True

            for rc in shape:
                del cell_to_block[rc]
            del block_size[block_id]

        return False

    if not dfs(0):
        return None

    return cell_to_block, block_size


def _build_block_adjacency(cell_to_block: Dict[Coord, int], R: int, C: int) -> Dict[int, Set[int]]:
    adj: Dict[int, Set[int]] = {}
    for (r, c), b in cell_to_block.items():
        adj.setdefault(b, set())
        for nb in _neighbors4(r, c, R, C):
            b2 = cell_to_block.get(nb)
            if b2 is None or b2 == b:
                continue
            adj[b].add(b2)
            adj.setdefault(b2, set()).add(b)
    return adj


def _color_blocks_backtracking(
    rng: random.Random,
    adj: Dict[int, Set[int]],
    palette: List[str],
    require_all_colors: bool
) -> Optional[Dict[int, str]]:
    """
    Graph color the blocks so adjacent blocks differ in color.
    Reuse allowed for non-adjacent blocks.
    """
    blocks = list(adj.keys())
    # degree heuristic
    blocks.sort(key=lambda b: len(adj[b]), reverse=True)

    color_of: Dict[int, str] = {}

    def can_use(b: int, col: str) -> bool:
        for nb in adj[b]:
            if color_of.get(nb) == col:
                return False
        return True

    def dfs(idx: int) -> bool:
        if idx == len(blocks):
            if require_all_colors:
                return set(palette).issubset(set(color_of.values()))
            return True

        b = blocks[idx]
        cols = palette[:]
        rng.shuffle(cols)

        # If we require all colors, try unused colors first
        if require_all_colors:
            used = set(color_of.values())
            cols = [c for c in cols if c not in used] + [c for c in cols if c in used]

        for col in cols:
            if can_use(b, col):
                color_of[b] = col
                if dfs(idx + 1):
                    return True
                del color_of[b]
        return False

    return color_of if dfs(0) else None


def _compute_sums_from_solution(sol: Dict[Coord, Val], rows: int, cols: int) -> Tuple[List[int], List[int]]:
    row_sums = [0] * rows
    col_sums = [0] * cols
    for (r, c), (n, _) in sol.items():
        row_sums[r] += n
        col_sums[c] += n
    return row_sums, col_sums


def construct_solution(cfg: ConstructConfig) -> Tuple[Dict[Coord, Val], Puzzle]:
    """
    Returns:
      - sol: dict[(r,c)] -> (n,col) full constructed solution
      - base_puzzle: Puzzle with row/col sums and no givens
    """
    R, C = cfg.rows, cfg.cols
    area = R * C
    palette = [c.upper() for c in cfg.palette]
    numbers = list(cfg.numbers)

    if cfg.require_all_numbers and not _area_feasible(R, C, numbers):
        raise ValueError(
            f"Grid too small to include all numbers at least once as blocks. "
            f"Need area >= sum(numbers)={sum(numbers)}, got {area}."
        )

    rng = random.Random(cfg.seed)
    style = (cfg.style or "BALANCED").upper().strip()

    for _attempt in range(cfg.max_attempts):
        # 1) choose block sizes with bias
        block_sizes = choose_block_sizes_biased(
            area=area,
            allowed_numbers=numbers,
            rng=rng,
            mode=style,  # SMALL/BALANCED/BIG/UNIFORM
            require_all_numbers=cfg.require_all_numbers,
            max_tries=2000,
        )
        if not block_sizes:
            continue

        # 2) partition grid into blocks (numbers only)
        part = _partition_into_blocks(rng, R, C, block_sizes)
        if not part:
            continue
        cell_to_block, block_size = part

        # Require each number used at least once as a block
        if cfg.require_all_numbers:
            used_block_sizes = set(block_size.values())
            if not set(numbers).issubset(used_block_sizes):
                continue

        # 3) build adjacency and color blocks
        adj = _build_block_adjacency(cell_to_block, R, C)

        # require_all_colors is only feasible if blocks >= colors
        require_colors = cfg.require_all_colors and (len(block_size) >= len(palette))

        colors = _color_blocks_backtracking(rng, adj, palette, require_all_colors=require_colors)
        if not colors:
            continue

        # If require_all_colors, ensure all present
        if require_colors:
            if not set(palette).issubset(set(colors.values())):
                continue

        # 4) build solution dict: each cell gets (block_size, block_color)
        sol: Dict[Coord, Val] = {}
        for (r, c), b in cell_to_block.items():
            n = block_size[b]
            col = colors[b]
            sol[(r, c)] = (n, col)

        # 5) compute sums and return base puzzle
        row_sums, col_sums = _compute_sums_from_solution(sol, R, C)
        base_puzzle = Puzzle(
            rows=R,
            cols=C,
            palette=palette,
            numbers=numbers,
            row_sums=row_sums,
            col_sums=col_sums,
            givens=[]
        )
        return sol, base_puzzle

    raise RuntimeError("Constructor failed after max_attempts. Try another seed or relax constraints.")