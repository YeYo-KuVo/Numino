from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Dict, List, Optional, Sequence, Tuple
import random

Coord = Tuple[int, int]          # (r, c)
Val = Tuple[int, str]            # (number, color)


@dataclass(frozen=True)
class Given:
    r: int
    c: int
    num: Optional[int] = None
    col: Optional[str] = None


@dataclass
class Puzzle:
    rows: int
    cols: int
    palette: List[str]                 # e.g. ["R","Y","B"]
    numbers: List[int]                 # e.g. [1,2,3,4,5]
    row_sums: List[int]                # len=rows
    col_sums: List[int]                # len=cols
    givens: List[Given]                # fixed num and/or color


class NuminoSolver:
    """
    Numino Classic solver (square grid, sum clues).

    Rules enforced:
    - Cells are labeled with (number, color)
    - Cells with the same (number,color) form 4-connected regions of size == number
    - Adjacent cells that belong to DIFFERENT blocks cannot share the same color
      (implemented as: if adjacent numbers differ, colors must differ)
    - Row and column sums match the clues
    """

    def __init__(self, puzzle: Puzzle, seed: Optional[int] = None):
        self.p = puzzle
        self.rng = random.Random(seed)

        self.R = puzzle.rows
        self.C = puzzle.cols
        self.cells: List[Coord] = [(r, c) for r in range(self.R) for c in range(self.C)]

        # Domain per cell: set of (n,col)
        self.dom: Dict[Coord, set[Val]] = {
            (r, c): {(n, col) for n in puzzle.numbers for col in puzzle.palette}
            for r in range(self.R) for c in range(self.C)
        }

        # Assignments: (r,c)->(n,col)
        self.assign: Dict[Coord, Val] = {}

        # Apply givens as domain restrictions
        for g in puzzle.givens:
            rc = (g.r, g.c)
            allowed = set(self.dom[rc])
            if g.num is not None:
                allowed = {(n, col) for (n, col) in allowed if n == g.num}
            if g.col is not None:
                allowed = {(n, col) for (n, col) in allowed if col == g.col}
            self.dom[rc] = allowed

        self.row_sum_now = [0] * self.R
        self.col_sum_now = [0] * self.C

    # ---------------- utilities ----------------
    def neighbors4(self, r: int, c: int) -> List[Coord]:
        out: List[Coord] = []
        if r > 0: out.append((r - 1, c))
        if r + 1 < self.R: out.append((r + 1, c))
        if c > 0: out.append((r, c - 1))
        if c + 1 < self.C: out.append((r, c + 1))
        return out

    def minmax_remaining_row(self, r: int) -> Tuple[int, int]:
        min_add = 0
        max_add = 0
        for c in range(self.C):
            rc = (r, c)
            if rc in self.assign:
                continue
            d = self.dom[rc]
            if not d:
                return (10**18, -10**18)
            nums = [n for (n, _) in d]
            min_add += min(nums)
            max_add += max(nums)
        return min_add, max_add

    def minmax_remaining_col(self, c: int) -> Tuple[int, int]:
        min_add = 0
        max_add = 0
        for r in range(self.R):
            rc = (r, c)
            if rc in self.assign:
                continue
            d = self.dom[rc]
            if not d:
                return (10**18, -10**18)
            nums = [n for (n, _) in d]
            min_add += min(nums)
            max_add += max(nums)
        return min_add, max_add

    def sums_ok_local(self, rc: Coord, v: Val) -> bool:
        r, c = rc
        n, _ = v

        rs = self.row_sum_now[r] + n
        cs = self.col_sum_now[c] + n
        if rs > self.p.row_sums[r] or cs > self.p.col_sums[c]:
            return False

        # Check row feasibility bounds after placing
        min_add = 0
        max_add = 0
        for cc in range(self.C):
            rc2 = (r, cc)
            if rc2 == rc or rc2 in self.assign:
                continue
            d = self.dom[rc2]
            if not d:
                return False
            nums = [nn for (nn, _) in d]
            min_add += min(nums)
            max_add += max(nums)
        if rs + min_add > self.p.row_sums[r] or rs + max_add < self.p.row_sums[r]:
            return False

        # Check col feasibility bounds after placing
        min_add = 0
        max_add = 0
        for rr in range(self.R):
            rc3 = (rr, c)
            if rc3 == rc or rc3 in self.assign:
                continue
            d = self.dom[rc3]
            if not d:
                return False
            nums = [nn for (nn, _) in d]
            min_add += min(nums)
            max_add += max(nums)
        if cs + min_add > self.p.col_sums[c] or cs + max_add < self.p.col_sums[c]:
            return False

        return True

    def color_adjacency_ok(self, rc: Coord, v: Val) -> bool:
        # If neighbor assigned with different number, colors must differ
        r, c = rc
        n, col = v
        for nb in self.neighbors4(r, c):
            if nb in self.assign:
                n2, col2 = self.assign[nb]
                if n2 != n and col2 == col:
                    return False
        return True

    def block_feasible(self, rc: Coord, v: Val) -> bool:
        """
        For the component containing rc with value v=(n,col):
        1) assigned connected size cannot exceed n
        2) reachable capacity of cells that could be v from rc must be >= n
        """
        r, c = rc
        n, _ = v

        # Count assigned same-value component adjacent to rc
        assigned_same: set[Coord] = set()
        q: deque[Coord] = deque()
        seen: set[Coord] = set()

        for nb in self.neighbors4(r, c):
            if nb in self.assign and self.assign[nb] == v:
                assigned_same.add(nb)
                q.append(nb)
                seen.add(nb)

        while q:
            cur = q.popleft()
            rr, cc = cur
            for nb in self.neighbors4(rr, cc):
                if nb in seen:
                    continue
                if nb in self.assign and self.assign[nb] == v:
                    seen.add(nb)
                    q.append(nb)
                    assigned_same.add(nb)

        if 1 + len(assigned_same) > n:
            return False

        # BFS reachable capacity: assigned same OR unassigned allowing v
        def allows(xy: Coord) -> bool:
            if xy in self.assign:
                return self.assign[xy] == v
            return v in self.dom[xy]

        reachable = 1
        q = deque([rc])
        visited = {rc}
        while q:
            cur = q.popleft()
            rr, cc = cur
            for nb in self.neighbors4(rr, cc):
                if nb in visited:
                    continue
                if allows(nb):
                    visited.add(nb)
                    q.append(nb)
                    reachable += 1

        return reachable >= n

    # ---------------- backtracking core ----------------
    def select_mrv(self) -> Coord:
        best: Optional[Coord] = None
        best_len = 10**18
        for rc in self.cells:
            if rc in self.assign:
                continue
            dlen = len(self.dom[rc])
            if dlen < best_len:
                best = rc
                best_len = dlen
                if dlen == 1:
                    break
        assert best is not None
        return best

    def order_values(self, rc: Coord) -> List[Val]:
        vals = list(self.dom[rc])
        self.rng.shuffle(vals)

        # LCV-ish: prefer values that eliminate fewer neighbor options due to color rule
        def impact(v: Val) -> int:
            r, c = rc
            n, col = v
            cnt = 0
            for nb in self.neighbors4(r, c):
                if nb in self.assign:
                    continue
                for (nn, cc) in self.dom[nb]:
                    if nn != n and cc == col:
                        cnt += 1
            return cnt

        vals.sort(key=impact)
        return vals

    def assign_val(self, rc: Coord, v: Val) -> None:
        self.assign[rc] = v
        r, c = rc
        self.row_sum_now[r] += v[0]
        self.col_sum_now[c] += v[0]

    def unassign_val(self, rc: Coord, v: Val) -> None:
        del self.assign[rc]
        r, c = rc
        self.row_sum_now[r] -= v[0]
        self.col_sum_now[c] -= v[0]

    def forward_check_prune(self, rc: Coord, v: Val) -> List[Tuple[Coord, Val]]:
        """
        Prune:
        - lock rc to v
        - in neighbors, remove values with same color but different number
        Returns list of removed (cell, value) so we can undo.
        """
        r, c = rc
        n, col = v
        removed: List[Tuple[Coord, Val]] = []

        # lock rc
        for w in list(self.dom[rc]):
            if w != v:
                self.dom[rc].remove(w)
                removed.append((rc, w))

        # prune neighbors
        for nb in self.neighbors4(r, c):
            if nb in self.assign:
                continue
            to_remove: List[Val] = []
            for (nn, cc) in self.dom[nb]:
                if nn != n and cc == col:
                    to_remove.append((nn, cc))
            for w in to_remove:
                if w in self.dom[nb]:
                    self.dom[nb].remove(w)
                    removed.append((nb, w))

        return removed

    def undo_prune(self, removed: List[Tuple[Coord, Val]]) -> None:
        for rc, v in reversed(removed):
            self.dom[rc].add(v)

    def is_complete(self) -> bool:
        return len(self.assign) == self.R * self.C

    def sums_exact_ok(self) -> bool:
        return self.row_sum_now == self.p.row_sums and self.col_sum_now == self.p.col_sums

    def complete_blocks_ok(self) -> bool:
        # every connected region of identical (n,col) must have size == n
        seen: set[Coord] = set()
        for r in range(self.R):
            for c in range(self.C):
                rc = (r, c)
                if rc in seen:
                    continue
                if rc not in self.assign:
                    return False
                v = self.assign[rc]
                n, _ = v
                q = deque([rc])
                seen.add(rc)
                comp: List[Coord] = [rc]
                while q:
                    rr, cc = q.popleft()
                    for nb in self.neighbors4(rr, cc):
                        if nb in seen:
                            continue
                        if nb in self.assign and self.assign[nb] == v:
                            seen.add(nb)
                            q.append(nb)
                            comp.append(nb)
                if len(comp) != n:
                    return False
        return True

    def global_bounds_ok(self) -> bool:
        for r in range(self.R):
            mn, mx = self.minmax_remaining_row(r)
            if self.row_sum_now[r] + mn > self.p.row_sums[r] or self.row_sum_now[r] + mx < self.p.row_sums[r]:
                return False
        for c in range(self.C):
            mn, mx = self.minmax_remaining_col(c)
            if self.col_sum_now[c] + mn > self.p.col_sums[c] or self.col_sum_now[c] + mx < self.p.col_sums[c]:
                return False
        return True

    def solve(self, find_two: bool = False, max_solutions: int = 2) -> List[Dict[Coord, Val]]:
        solutions: List[Dict[Coord, Val]] = []

        def dfs() -> bool:
            if not self.global_bounds_ok():
                return False

            if self.is_complete():
                if self.sums_exact_ok() and self.complete_blocks_ok():
                    solutions.append(dict(self.assign))
                    return True
                return False

            rc = self.select_mrv()
            for v in self.order_values(rc):
                if not self.sums_ok_local(rc, v):
                    continue
                if not self.color_adjacency_ok(rc, v):
                    continue
                if not self.block_feasible(rc, v):
                    continue

                self.assign_val(rc, v)
                removed = self.forward_check_prune(rc, v)

                ok = dfs()

                self.undo_prune(removed)
                self.unassign_val(rc, v)

                if ok and not find_two:
                    return True
                if find_two and len(solutions) >= max_solutions:
                    return True

            return False

        dfs()
        return solutions


# -------- public helper functions --------
def solve(puzzle: Puzzle, seed: Optional[int] = None) -> Optional[Dict[Coord, Val]]:
    s = NuminoSolver(puzzle, seed=seed)
    sols = s.solve(find_two=False)
    return sols[0] if sols else None


def count_solutions(puzzle: Puzzle, limit: int = 2, seed: Optional[int] = None) -> int:
    s = NuminoSolver(puzzle, seed=seed)
    sols = s.solve(find_two=True, max_solutions=limit)
    return len(sols)


def solution_to_grid(rows: int, cols: int, sol: Dict[Coord, Val]) -> List[List[Val]]:
    grid: List[List[Val]] = [[(0, "") for _ in range(cols)] for _ in range(rows)]
    for (r, c), v in sol.items():
        grid[r][c] = v
    return grid