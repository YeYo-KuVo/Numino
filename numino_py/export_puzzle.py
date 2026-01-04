# export_puzzle.py

import json
from pathlib import Path
from typing import Dict

from solver import Puzzle, Coord, Val


def export_single_puzzle(
    puzzle: Puzzle,
    solution: Dict[Coord, Val] | None,
    puzzle_id: str,
    bias: str,
    difficulty: int = 0,
    output_path: str = "docs/puzzles.json",
    include_solution: bool = False,
) -> None:
    """
    Export ONE Numino puzzle to JSON for static web play.
    Appends the puzzle to docs/puzzles.json if it exists.
    Solutions are never exported unless explicitly requested.
    """

    puzzle_obj = {
        "id": puzzle_id,
        "grid": {
            "rows": puzzle.rows,
            "cols": puzzle.cols,
        },
        "allowed": {
            "numbers": list(puzzle.numbers),
            "colors": list(puzzle.palette),
        },
        "bias": bias,
        "difficulty": difficulty,
        "constraints": {
            "row_sums": list(puzzle.row_sums),
            "col_sums": list(puzzle.col_sums),
        },
        "givens": [
            {
                "r": g.r,
                "c": g.c,
                "num": g.num,
                "col": g.col,
            }
            for g in puzzle.givens
        ],
    }

    if include_solution:
        if solution is None:
            raise ValueError("include_solution=True requires a non-None solution dict")
        puzzle_obj["solution"] = [
            {
                "r": r,
                "c": c,
                "num": solution[(r, c)][0],
                "col": solution[(r, c)][1],
            }
            for r in range(puzzle.rows)
            for c in range(puzzle.cols)
        ]

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists():
        with out.open("r", encoding="utf-8") as f:
            existing = json.load(f)
        puzzles = existing.get("puzzles", [])
    else:
        puzzles = []

    puzzles.append(puzzle_obj)

    data = {
        "version": 1,
        "puzzles": puzzles,
    }

    with out.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"✓ Exported puzzle → {out.resolve()}")