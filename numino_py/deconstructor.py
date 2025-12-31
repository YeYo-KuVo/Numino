from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set
import random
from collections import deque

from solver import Puzzle, Given, count_solutions, Coord, Val


@dataclass
class MaskCell:
    show_num: bool = True
    show_col: bool = True


@dataclass
class DeconstructConfig:
    seed: int
    difficulty: str = "MEDIUM"  # EASY | MEDIUM | HARD | EXPERT
    max_steps: int = 50_000
    strategy: str = "any"       # any | number_first | color_first


def difficulty_to_target_reveals(difficulty: str, rows: int, cols: int) -> int:
    """
    Convert difficulty to a target number of revealed attributes.
    Attribute = one number reveal OR one color reveal.
    """
    cells = rows * cols
    diff = difficulty.upper()

    if diff == "EASY":
        per_cell = 1.30
    elif diff == "MEDIUM":
        per_cell = 1.05
    elif diff == "HARD":
        per_cell = 0.85
    elif diff == "EXPERT":
        per_cell = 0.65
    else:
        raise ValueError(f"Unknown difficulty: {difficulty} (use EASY/MEDIUM/HARD/EXPERT)")

    # Always keep at least a small floor so tiny boards don't become empty
    return max(8, int(cells * per_cell))


class DeconstructorStepper:
    """
    Removes one clue at a time while preserving uniqueness.

    New: difficulty tiers (target_reveals derived from difficulty).

    Quality rule:
      - No block may remain fully revealed (all cells show both num+color).
      - After each accepted removal, sanitize blocks to enforce this rule.
    """

    def __init__(self, base_puzzle: Puzzle, solution: Dict[Coord, Val], cfg: DeconstructConfig):
        self.base = base_puzzle
        self.solution = solution
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)

        self.rows = base_puzzle.rows
        self.cols = base_puzzle.cols

        # derived stopping threshold
        self.target_reveals = difficulty_to_target_reveals(cfg.difficulty, self.rows, self.cols)

        # Mask starts fully revealed
        self.mask: List[List[MaskCell]] = [
            [MaskCell(True, True) for _ in range(self.cols)]
            for _ in range(self.rows)
        ]

        # Candidate list of removable (r,c,part)
        self.candidates: List[Tuple[int, int, str]] = []
        for r in range(self.rows):
            for c in range(self.cols):
                self.candidates.append((r, c, "num"))
                self.candidates.append((r, c, "col"))

        # For higher difficulties, bias removal order
        # - Expert: prefer removing colors first (often less structural than numbers)
        diff = cfg.difficulty.upper()
        if diff == "EXPERT":
            # put color removals early
            self.candidates.sort(key=lambda x: 0 if x[2] == "col" else 1)
        elif diff == "HARD":
            # mild preference for colors first
            self.candidates.sort(key=lambda x: 0 if x[2] == "col" else 1)

        self.rng.shuffle(self.candidates)
        self.steps_done = 0

    # ---------------- counts / puzzle build ----------------
    def reveals_count(self) -> int:
        cnt = 0
        for r in range(self.rows):
            for c in range(self.cols):
                if self.mask[r][c].show_num:
                    cnt += 1
                if self.mask[r][c].show_col:
                    cnt += 1
        return cnt

    def build_givens_from_mask(self) -> List[Given]:
        givens: List[Given] = []
        for r in range(self.rows):
            for c in range(self.cols):
                n, col = self.solution[(r, c)]
                mc = self.mask[r][c]
                if mc.show_num or mc.show_col:
                    givens.append(
                        Given(
                            r=r,
                            c=c,
                            num=n if mc.show_num else None,
                            col=col if mc.show_col else None
                        )
                    )
        return givens

    def current_puzzle(self) -> Puzzle:
        return Puzzle(
            rows=self.base.rows,
            cols=self.base.cols,
            palette=self.base.palette,
            numbers=self.base.numbers,
            row_sums=self.base.row_sums,
            col_sums=self.base.col_sums,
            givens=self.build_givens_from_mask()
        )

    # ---------------- block utilities (quality rule) ----------------
    def _neighbors4(self, r: int, c: int) -> List[Coord]:
        out: List[Coord] = []
        if r > 0: out.append((r - 1, c))
        if r + 1 < self.rows: out.append((r + 1, c))
        if c > 0: out.append((r, c - 1))
        if c + 1 < self.cols: out.append((r, c + 1))
        return out

    def _blocks_from_solution(self) -> List[List[Coord]]:
        seen: Set[Coord] = set()
        blocks: List[List[Coord]] = []

        for r in range(self.rows):
            for c in range(self.cols):
                rc = (r, c)
                if rc in seen:
                    continue
                v = self.solution[rc]
                q = deque([rc])
                seen.add(rc)
                block = [rc]
                while q:
                    rr, cc = q.popleft()
                    for nb in self._neighbors4(rr, cc):
                        if nb in seen:
                            continue
                        if self.solution[nb] == v:
                            seen.add(nb)
                            q.append(nb)
                            block.append(nb)
                blocks.append(block)
        return blocks

    def _block_fully_revealed(self, block: List[Coord]) -> bool:
        for r, c in block:
            mc = self.mask[r][c]
            if not (mc.show_num and mc.show_col):
                return False
        return True

    def _try_remove_from_block(self, block: List[Coord]) -> bool:
        candidates: List[Tuple[int, int, str]] = []
        for r, c in block:
            candidates.append((r, c, "num"))
            candidates.append((r, c, "col"))
        self.rng.shuffle(candidates)

        for r, c, part in candidates:
            prev_num = self.mask[r][c].show_num
            prev_col = self.mask[r][c].show_col

            if part == "num" and not prev_num:
                continue
            if part == "col" and not prev_col:
                continue

            if part == "num":
                self.mask[r][c].show_num = False
            else:
                self.mask[r][c].show_col = False

            puzzle = self.current_puzzle()
            nsol = count_solutions(puzzle, limit=2, seed=self.cfg.seed)

            if nsol == 1:
                return True

            # revert
            self.mask[r][c].show_num = prev_num
            self.mask[r][c].show_col = prev_col

        return False

    def _ensure_no_fully_revealed_blocks(self) -> None:
        blocks = self._blocks_from_solution()
        for block in blocks:
            if self._block_fully_revealed(block):
                self._try_remove_from_block(block)

    # ---------------- removal candidate picker ----------------
    def _pick_next_candidate(self) -> Optional[Tuple[int, int, str]]:
        if not self.candidates:
            return None

        # Strategy filter
        for idx, (r, c, part) in enumerate(self.candidates):
            cell = self.mask[r][c]
            if part == "num" and not cell.show_num:
                continue
            if part == "col" and not cell.show_col:
                continue

            if self.cfg.strategy == "number_first" and part != "num":
                continue
            if self.cfg.strategy == "color_first" and part != "col":
                continue

            self.candidates.pop(idx)
            return (r, c, part)

        # Fallback any removable
        for idx, (r, c, part) in enumerate(self.candidates):
            cell = self.mask[r][c]
            if part == "num" and cell.show_num:
                self.candidates.pop(idx)
                return (r, c, part)
            if part == "col" and cell.show_col:
                self.candidates.pop(idx)
                return (r, c, part)

        return None

    # ---------------- main step API ----------------
    def step(self) -> Dict:
        """
        Remove exactly one clue (num or color), only if uniqueness remains.
        """
        if self.steps_done >= self.cfg.max_steps:
            self._ensure_no_fully_revealed_blocks()
            return {"ok": False, "removed": None, "reveals": self.reveals_count(), "reason": "max_steps_reached"}

        if self.reveals_count() <= self.target_reveals:
            self._ensure_no_fully_revealed_blocks()
            return {"ok": False, "removed": None, "reveals": self.reveals_count(), "reason": "target_reached"}

        self.steps_done += 1

        # Expert tries harder each step
        diff = self.cfg.difficulty.upper()
        tries_limit = 2000 if diff == "EXPERT" else 800 if diff == "HARD" else 500

        tries = 0
        while tries < tries_limit and self.candidates:
            tries += 1
            cand = self._pick_next_candidate()
            if cand is None:
                break

            r, c, part = cand

            prev_num = self.mask[r][c].show_num
            prev_col = self.mask[r][c].show_col

            if part == "num":
                self.mask[r][c].show_num = False
            else:
                self.mask[r][c].show_col = False

            puzzle = self.current_puzzle()
            nsol = count_solutions(puzzle, limit=2, seed=self.cfg.seed)

            if nsol == 1:
                self._ensure_no_fully_revealed_blocks()
                return {"ok": True, "removed": (r, c, part), "reveals": self.reveals_count(), "reason": "unique_kept"}

            # revert
            self.mask[r][c].show_num = prev_num
            self.mask[r][c].show_col = prev_col

        self._ensure_no_fully_revealed_blocks()
        return {"ok": False, "removed": None, "reveals": self.reveals_count(), "reason": "no_more_unique_removals"}

    def run_to_target(self) -> Puzzle:
        """
        Auto-deconstruct until target reached or no more safe removals.
        """
        while True:
            res = self.step()
            if not res["ok"]:
                break
        return self.current_puzzle()