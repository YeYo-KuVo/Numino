# generate_and_export.py

from datetime import date
from pathlib import Path
import json

from calibration import CalibrationResult
from editor import generate_puzzle_from_calibration
from export_puzzle import export_single_puzzle


def append_private_solution(
    puzzle_id: str,
    solution: dict,
    output_path: str = "private/solutions.json",
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists():
        with out.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    data[puzzle_id] = {
        f"{r},{c}": {"num": num, "col": col}
        for (r, c), (num, col) in solution.items()
    }

    with out.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"✓ Private solution saved → {out}")


def main():
    # ---- configure ONE puzzle here ----
    cfg = CalibrationResult(
        rows=4,
        cols=4,
        numbers=[1, 2, 3],
        colors=["B", "Y", "V"],
        balance="BALANCED",
        seed=12345,
    )

    puzzle_id = date.today().isoformat()

    puzzle, solution, bias, _pid, difficulty = generate_puzzle_from_calibration(cfg)

    # Public export (NO solution)
    export_single_puzzle(
        puzzle=puzzle,
        solution=None,
        puzzle_id=puzzle_id,
        bias=bias,
        difficulty=0,
        output_path="docs/puzzles.json",
        include_solution=False,
    )

    # Private export (solution only)
    append_private_solution(puzzle_id, solution)


if __name__ == "__main__":
    main()