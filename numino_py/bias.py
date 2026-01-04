from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Sequence
import random
import math

BiasMode = str  # "SMALL" | "BALANCED" | "BIG" | "UNIFORM"


def _weighted_choice(rng: random.Random, items: List[int], weights: List[float]) -> int:
    total = sum(weights)
    r = rng.random() * total
    acc = 0.0
    for item, w in zip(items, weights):
        acc += w
        if r <= acc:
            return item
    return items[-1]


def _base_weights(fits: List[int], mode: BiasMode) -> List[float]:
    """
    Local preference curve (kept mild).
    Global behavior is controlled separately via block-count steering.
    """
    mode = mode.upper()

    if mode == "UNIFORM":
        return [1.0 for _ in fits]

    if mode == "SMALL":
        return [1.0 / (n ** 1.1) for n in fits]

    if mode == "BIG":
        return [float(n ** 1.6) for n in fits]

    # BALANCED
    return [float(n ** 0.5) for n in fits]


def _target_block_count(area: int, nums: List[int], mode: BiasMode) -> float:
    """
    Define a soft target for number of blocks.
    This is what the player actually perceives as bias.
    """
    n_min = min(nums)
    n_max = max(nums)
    n_mean = sum(nums) / len(nums)

    mode = mode.upper()
    if mode == "SMALL":
        return area / n_min
    if mode == "BIG":
        return area / n_max
    if mode == "UNIFORM":
        return area / n_mean

    # BALANCED
    return area / n_mean


def choose_block_sizes_biased(
    *,
    area: int,
    allowed_numbers: Sequence[int],
    rng: random.Random,
    mode: BiasMode = "BALANCED",
    require_all_numbers: bool = True,
    max_tries: int = 3000,
) -> Optional[List[int]]:
    """
    Returns a list of block sizes summing to `area`.

    Improvement:
    - Bias is driven by a global target block count (perceptible).
    - Local picks are gently steered toward that target.
    """
    nums = sorted(set(int(n) for n in allowed_numbers))
    if not nums:
        return None

    if require_all_numbers and sum(nums) > area:
        return None

    for _ in range(max_tries):
        remaining = area
        blocks: List[int] = []

        # Seed with one of each number if required
        if require_all_numbers:
            blocks.extend(nums)
            remaining -= sum(nums)

        target_blocks = _target_block_count(area, nums, mode)

        guard = 10000
        while remaining > 0 and guard > 0:
            guard -= 1
            fits = [n for n in nums if n <= remaining]
            if not fits:
                break

            # Base local weights
            w = _base_weights(fits, mode)

            # ---- Global steering toward target block count ----
            current_blocks = len(blocks)
            delta = target_blocks - current_blocks

            # If we want MORE blocks, favor smaller sizes.
            # If we want FEWER blocks, favor larger sizes.
            steer = []
            for n, weight in zip(fits, w):
                if delta > 0:
                    factor = (max(nums) / n) ** 0.6
                else:
                    factor = (n / min(nums)) ** 0.6
                steer.append(weight * factor)

            pick = _weighted_choice(rng, fits, steer)
            blocks.append(pick)
            remaining -= pick

        if remaining == 0:
            rng.shuffle(blocks)
            return blocks

    return None