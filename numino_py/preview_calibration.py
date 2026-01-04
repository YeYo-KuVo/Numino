from __future__ import annotations

import random
from collections import Counter, defaultdict
from itertools import combinations
from typing import List, Tuple, Dict, Set

# Import the SAME rules used by the calibration UI
from calibration import (
    max_number_allowed,
    max_distinct_numbers_allowed,
    blockiness,
    max_colors_allowed,
    balance_availability,
)

BALANCE_OPTIONS = ["SMALL", "BALANCED", "BIG"]
COLOR_OPTIONS = ["R", "Y", "B", "G", "O"]

# ---------- knobs ----------
SEED = 12345
SAMPLES = 300              # how many random calibrations to test
GRID_RANGE = range(3, 10)  # 3..9
# --------------------------


def pick_subset(rng: random.Random, items: List[int], k: int) -> List[int]:
    items = list(items)
    rng.shuffle(items)
    return sorted(items[:k])


def main():
    rng = random.Random(SEED)

    results = []
    stats = Counter()
    by_area = defaultdict(Counter)

    for _ in range(SAMPLES):
        rows = rng.choice(list(GRID_RANGE))
        cols = rng.choice(list(GRID_RANGE))
        A = rows * cols

        # Allowed numbers by grid
        maxN = max_number_allowed(rows, cols)
        allowed_numbers = list(range(1, maxN + 1))

        # Pick how many distinct numbers (respect cap)
        max_k = min(len(allowed_numbers), max_distinct_numbers_allowed(A))
        k = rng.randint(1, max_k)

        nums = pick_subset(rng, allowed_numbers, k)

        # Enforce your Fix A rule for small grids: must include 1
        fixA_required = (A <= 16)
        fixA_ok = (not fixA_required) or (1 in nums)

        # Compute blockiness metric (use selected nums)
        B = blockiness(A, nums)

        # Colors cap (current rule)
        col_cap = max_colors_allowed(A, B)

        # Balance availability
        n_min, n_max = min(nums), max(nums)
        rng_width = n_max - n_min
        bal_ok = balance_availability(A, n_min, n_max, rng_width, B)
        small_enabled = bal_ok["SMALL"]
        big_enabled = bal_ok["BIG"]

        # Record
        results.append((rows, cols, A, nums, B, col_cap, small_enabled, big_enabled, fixA_ok))

        stats["total"] += 1
        stats[f"colors_cap_{col_cap}"] += 1
        stats["small_enabled"] += int(small_enabled)
        stats["big_enabled"] += int(big_enabled)
        stats["fixA_rejected"] += int(not fixA_ok)

        # Area bucket stats
        area_bucket = A
        by_area[area_bucket]["count"] += 1
        by_area[area_bucket][f"cap_{col_cap}"] += 1
        by_area[area_bucket]["small_on"] += int(small_enabled)
        by_area[area_bucket]["big_on"] += int(big_enabled)
        by_area[area_bucket]["fixA_rej"] += int(not fixA_ok)

    # ---------- Summary ----------
    print("\n=== Calibration Preview Summary ===")
    print(f"SAMPLES = {SAMPLES} (seed={SEED})")
    print()

    def pct(x: int, denom: int) -> float:
        return (100.0 * x / denom) if denom else 0.0

    total = stats["total"]
    print(f"Colors cap:")
    for cap in sorted({2,3,4}):
        if stats.get(f"colors_cap_{cap}", 0) > 0:
            print(f"  cap={cap}: {stats[f'colors_cap_{cap}']} ({pct(stats[f'colors_cap_{cap}'], total):.1f}%)")

    print()
    print(f"Balance availability:")
    print(f"  SMALL enabled: {stats['small_enabled']} ({pct(stats['small_enabled'], total):.1f}%)")
    print(f"  BIG enabled:   {stats['big_enabled']} ({pct(stats['big_enabled'], total):.1f}%)")

    print()
    print(f"Fix A (A<=16 requires number 1):")
    print(f"  rejected configs: {stats['fixA_rejected']} ({pct(stats['fixA_rejected'], total):.1f}%)")

    print("\n--- By Area (only areas seen) ---")
    for A in sorted(by_area.keys()):
        c = by_area[A]["count"]
        cap2 = by_area[A].get("cap_2", 0)
        cap3 = by_area[A].get("cap_3", 0)
        cap4 = by_area[A].get("cap_4", 0)
        sm = by_area[A]["small_on"]
        bg = by_area[A]["big_on"]
        rej = by_area[A]["fixA_rej"]
        print(
            f"A={A:2d}  n={c:3d}  cap2={cap2:3d} ({pct(cap2,c):5.1f}%)"
            f"  cap3={cap3:3d} ({pct(cap3,c):5.1f}%)"
            f"  SMALL={sm:3d} ({pct(sm,c):5.1f}%)"
            f"  BIG={bg:3d} ({pct(bg,c):5.1f}%)"
            f"  fixA_rej={rej:3d} ({pct(rej,c):5.1f}%)"
        )

    # Optional: print a few random examples that look "weird"
    print("\n--- Examples (first 12) ---")
    for (rows, cols, A, nums, B, cap, sm, bg, ok) in results[:12]:
        print(f"{rows}x{cols} A={A:2d} nums={nums} B={B:5.1f} cap={cap} SMALL={sm} BIG={bg} fixA_ok={ok}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()