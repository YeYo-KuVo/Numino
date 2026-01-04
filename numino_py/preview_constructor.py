from __future__ import annotations

from collections import Counter, deque
from typing import Dict, Tuple, List
from constructor import ConstructConfig, construct_solution
from solver import Coord, Val

ROWS, COLS = 5, 5
PALETTE = ["R", "Y", "B"]
NUMBERS = [1, 2, 3, 4, 5]

STYLES = ["SMALL", "BALANCED", "BIG"]   # compare these
SAMPLES = 30
SEED0 = 202501010101


def neighbors4(r: int, c: int, R: int, C: int) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    if r > 0:
        out.append((r - 1, c))
    if r + 1 < R:
        out.append((r + 1, c))
    if c > 0:
        out.append((r, c - 1))
    if c + 1 < C:
        out.append((r, c + 1))
    return out


def block_histogram(sol: Dict[Coord, Val], rows: int, cols: int) -> Counter:
    """
    Count blocks by size in a fully constructed solution.
    We treat a block as a connected component of identical (n, color).
    """
    seen = set()
    hist = Counter()

    for r in range(rows):
        for c in range(cols):
            rc = (r, c)
            if rc in seen:
                continue

            v = sol[rc]
            n, _ = v
            q = deque([rc])
            seen.add(rc)

            while q:
                rr, cc = q.popleft()
                for nb in neighbors4(rr, cc, rows, cols):
                    if nb in seen:
                        continue
                    if sol[nb] == v:
                        seen.add(nb)
                        q.append(nb)

            # Each connected component corresponds to one block of size n
            hist[n] += 1

    return hist


def run_style(style: str) -> Counter:
    agg = Counter()
    for i in range(SAMPLES):
        seed = SEED0 + i
        cfg = ConstructConfig(
            rows=ROWS,
            cols=COLS,
            palette=PALETTE,
            numbers=NUMBERS,
            seed=seed,
            style=style,
            require_all_numbers=True,
            require_all_colors=True,
            max_attempts=300,
        )
        sol, _ = construct_solution(cfg)
        h = block_histogram(sol, ROWS, COLS)
        agg.update(h)
    return agg


def main():
    print("\n=== Numino Constructor Style Comparison ===\n")
    print(f"Grid: {ROWS}x{COLS} | Numbers: {NUMBERS} | Colors: {PALETTE}")
    print(f"Samples per style: {SAMPLES}\n")

    results: Dict[str, Counter] = {}
    for style in STYLES:
        results[style] = run_style(style)

    header = "size %  | " + " | ".join(f"{s:9s}" for s in STYLES)
    print(header)
    print("-" * len(header))

    # Row per size: percent of blocks that are that size
    for k in NUMBERS:
        row = [f"{k:<6} |"]
        for style in STYLES:
            agg = results[style]
            total = sum(agg.values())
            pct = (agg.get(k, 0) / total * 100.0) if total else 0.0
            row.append(f"{pct:8.1f}% ")
        print(" ".join(row))

    print("\n--- Small vs Big block share (by block count) ---")
    for style in STYLES:
        agg = results[style]
        total = sum(agg.values())
        small = agg.get(1, 0) + agg.get(2, 0) + agg.get(3, 0)
        big = agg.get(4, 0) + agg.get(5, 0)
        print(
            f"{style:9s}: small(1-3)={(small/total*100):5.1f}%  "
            f"big(4-5)={(big/total*100):5.1f}%   total_blocks={total}"
        )

    print("\nDone.\n")


if __name__ == "__main__":
    main()