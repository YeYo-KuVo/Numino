import tkinter as tk
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict
from datetime import datetime

from solver import Puzzle, Coord, Val
from constructor import ConstructConfig, construct_solution
from deconstructor import DeconstructConfig, DeconstructorStepper


# --------- UI styling ---------
CELL_BG_DEFAULT = "#ffffff"
BORDER_SELECTED = "#222222"
BORDER_NORMAL = "#cccccc"

TEXT_COLOR = "#000000"       # numbers inside cells (always black)
SUM_TEXT_COLOR = "#f1f3f5"   # sums + UI text (light gray/white)

COLOR_KEYS = {
    "r": "#ff6b6b",  # red
    "y": "#ffe066",  # yellow
    "b": "#74c0fc",  # blue
    "g": "#63e6be",  # green
    "o": "#ffa94d",  # orange
}
SOL_TO_KEY = {"R": "r", "Y": "y", "B": "b", "G": "g", "O": "o"}
KEY_TO_SOL = {v: k for k, v in SOL_TO_KEY.items()}

STYLE_OPTIONS = ["BALANCED", "SMALL_BLOCKY", "LARGE_BLOCKY", "UNIFORM"]


def _default_seed_timestamp_seconds() -> int:
    return int(datetime.now().strftime("%Y%m%d%H%M%S"))


def _parse_color_keys(text: str) -> List[str]:
    s = text.strip().lower()
    if not s:
        return ["R", "Y", "B"]
    parts = s.replace(",", " ").split()
    out: List[str] = []
    for p in parts:
        if p not in ("r", "y", "b", "g", "o"):
            raise ValueError("Colors must be from: r y b g o")
        out.append(p.upper())
    return out


def _parse_numbers(text: str) -> List[int]:
    s = text.strip()
    if not s:
        return [1, 2, 3, 4, 5]
    parts = s.replace(",", " ").split()
    nums = [int(x) for x in parts]
    if any(n <= 0 for n in nums):
        raise ValueError("Numbers must be positive integers.")
    return nums


def _parse_style(text: str) -> str:
    s = text.strip().upper()
    if not s:
        return "BALANCED"
    if s not in STYLE_OPTIONS:
        raise ValueError(f"Style must be one of: {', '.join(STYLE_OPTIONS)}")
    return s


@dataclass
class CellState:
    num: Optional[int] = None
    color_key: Optional[str] = None  # r,y,b,g,o


class PlayEditor(tk.Tk):
    """
    Single-grid Numino Play UI with:
      - Undo (multi-step)
      - Reset
      - Allowed numbers/colors display
      - Auto status: Playing -> Incorrect/Congratulations when complete
    """

    def __init__(self, puzzle: Puzzle, solution: Dict[Coord, Val]):
        super().__init__()
        self.puzzle = puzzle
        self.solution = solution
        self.R = puzzle.rows
        self.C = puzzle.cols

        self.title("Numino — Play")

        # Givens map (r,c) -> (num?, col?)
        self.givens_map: Dict[Tuple[int, int], Tuple[Optional[int], Optional[str]]] = {}
        for g in puzzle.givens:
            self.givens_map[(g.r, g.c)] = (g.num, g.col)

        # Locks
        self.lock_num = [[False] * self.C for _ in range(self.R)]
        self.lock_col = [[False] * self.C for _ in range(self.R)]
        for (r, c), (n, col) in self.givens_map.items():
            if n is not None:
                self.lock_num[r][c] = True
            if col is not None:
                self.lock_col[r][c] = True

        # Player state (starts with givens)
        self.state: List[List[CellState]] = [[CellState() for _ in range(self.C)] for _ in range(self.R)]
        for r in range(self.R):
            for c in range(self.C):
                n, col = self.givens_map.get((r, c), (None, None))
                self.state[r][c].num = n
                self.state[r][c].color_key = SOL_TO_KEY.get(col, None) if col else None

        # Snapshot for Reset
        self.initial_state = self._snapshot_state()

        # Undo stack: list of snapshots
        self.undo_stack: List[List[List[Tuple[Optional[int], Optional[str]]]]] = []

        self.selected: Optional[Tuple[int, int]] = None
        self.cells: List[List[tk.Label]] = []
        self.status_label: Optional[tk.Label] = None

        self.undo_btn: Optional[tk.Button] = None

        self._build_ui()
        self._render_all()
        self._update_status()
        self._update_undo_button()

        # Bind keys
        self.bind("<KeyPress>", self._on_keypress)
        self.bind("<Escape>", self._on_escape)
        self.bind("<Delete>", self._on_delete_color)
        self.bind("<BackSpace>", self._on_delete_color)

        # Undo shortcuts
        self.bind_all("<Command-z>", self._on_undo)   # macOS
        self.bind_all("<Control-z>", self._on_undo)   # Windows/Linux

        self.focus_force()

    # ---------- Undo helpers ----------
    def _snapshot_state(self) -> List[List[Tuple[Optional[int], Optional[str]]]]:
        snap: List[List[Tuple[Optional[int], Optional[str]]]] = []
        for r in range(self.R):
            row = []
            for c in range(self.C):
                st = self.state[r][c]
                row.append((st.num, st.color_key))
            snap.append(row)
        return snap

    def _restore_snapshot(self, snap: List[List[Tuple[Optional[int], Optional[str]]]]) -> None:
        for r in range(self.R):
            for c in range(self.C):
                n, ck = snap[r][c]
                self.state[r][c].num = n
                self.state[r][c].color_key = ck

    def _push_undo(self) -> None:
        self.undo_stack.append(self._snapshot_state())
        self._update_undo_button()

    def _update_undo_button(self) -> None:
        if self.undo_btn is None:
            return
        self.undo_btn.config(state=("normal" if self.undo_stack else "disabled"))

    def _on_undo(self, _event=None) -> None:
        if not self.undo_stack:
            return
        snap = self.undo_stack.pop()
        self._restore_snapshot(snap)
        self.selected = None
        self._render_all()
        self._update_status()
        self._update_undo_button()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        outer = tk.Frame(self, padx=12, pady=12)
        outer.pack()

        # Top bar: Undo + Reset
        topbar = tk.Frame(outer)
        topbar.pack(fill="x", pady=(0, 6))

        self.undo_btn = tk.Button(topbar, text="Undo", command=self._on_undo)
        self.undo_btn.pack(side="left", padx=(0, 8))

        reset_btn = tk.Button(topbar, text="Reset", command=self._on_reset)
        reset_btn.pack(side="left")

        # NEW: Allowed numbers/colors info
        allowed_nums = ", ".join(map(str, self.puzzle.numbers))
        allowed_cols = ", ".join(self.puzzle.palette)
        info_text = f"Allowed numbers: {allowed_nums}    Allowed colors: {allowed_cols}    (keys: r y b g o)"

        info = tk.Label(
            outer,
            text=info_text,
            fg=SUM_TEXT_COLOR,
            bg=self["bg"],
            font=("Helvetica", 12, "bold"),
            padx=6,
            pady=4,
        )
        info.pack(pady=(0, 10))

        # Grid frame with sums
        frame = tk.Frame(outer)
        frame.pack()

        tk.Label(frame, text="", width=4, height=2, bg=self["bg"]).grid(row=0, column=0)

        # Column sums (light)
        for c in range(self.C):
            tk.Label(
                frame,
                text=str(self.puzzle.col_sums[c]),
                width=4, height=2,
                font=("Helvetica", 12, "bold"),
                fg=SUM_TEXT_COLOR,
                bg=self["bg"],
            ).grid(row=0, column=c + 1, padx=1, pady=1)

        # Rows + cells
        self.cells = []
        for r in range(self.R):
            tk.Label(
                frame,
                text=str(self.puzzle.row_sums[r]),
                width=4, height=2,
                font=("Helvetica", 12, "bold"),
                fg=SUM_TEXT_COLOR,
                bg=self["bg"],
            ).grid(row=r + 1, column=self.C + 1, padx=1, pady=1)

            row_widgets: List[tk.Label] = []
            for c in range(self.C):
                lbl = tk.Label(
                    frame,
                    text="",
                    width=4,
                    height=2,
                    bg=CELL_BG_DEFAULT,
                    fg=TEXT_COLOR,
                    relief="solid",
                    bd=1,
                    font=("Helvetica", 16, "bold"),
                    highlightthickness=1,
                    highlightbackground=BORDER_NORMAL,
                )
                lbl.grid(row=r + 1, column=c + 1, padx=1, pady=1, sticky="nsew")
                lbl.bind("<Button-1>", lambda e, rr=r, cc=c: self._select(rr, cc))
                row_widgets.append(lbl)
            self.cells.append(row_widgets)

        self.status_label = tk.Label(self, text="", padx=12, pady=10, font=("Helvetica", 16, "bold"))
        self.status_label.pack()

        tk.Label(
            self,
            text="Click a cell, type r/y/b/g/o for color, 1–9 for number. "
                 "0 clears number. Delete clears color. Esc unselect. Cmd+Z/Ctrl+Z = Undo. Givens locked.",
            padx=12, pady=6
        ).pack()

    # ---------- Actions ----------
    def _on_reset(self) -> None:
        self._restore_snapshot(self.initial_state)
        self.undo_stack.clear()
        self.selected = None
        self._render_all()
        self._update_status()
        self._update_undo_button()

    def _select(self, r: int, c: int) -> None:
        if self.selected is not None:
            pr, pc = self.selected
            self.selected = None
            self._render_cell(pr, pc)
        self.selected = (r, c)
        self._render_cell(r, c)
        self.focus_force()

    def _on_escape(self, _event=None) -> None:
        if self.selected is None:
            return
        r, c = self.selected
        self.selected = None
        self._render_cell(r, c)

    def _on_delete_color(self, _event=None) -> None:
        if self.selected is None:
            return
        r, c = self.selected
        if self.lock_col[r][c]:
            return
        if self.state[r][c].color_key is None:
            return
        self._push_undo()
        self.state[r][c].color_key = None
        self._render_cell(r, c)
        self._update_status()

    def _on_keypress(self, event: tk.Event) -> None:
        if self.selected is None:
            return
        r, c = self.selected
        ch = (event.char or "").lower()

        # 0 clears number
        if ch == "0":
            if self.lock_num[r][c]:
                return
            if self.state[r][c].num is None:
                return
            self._push_undo()
            self.state[r][c].num = None
            self._render_cell(r, c)
            self._update_status()
            return

        # digits set number (single digit)
        if ch.isdigit():
            n = int(ch)
            if n == 0:
                return
            if self.lock_num[r][c]:
                return
            if self.state[r][c].num == n:
                return
            self._push_undo()
            self.state[r][c].num = n
            self._render_cell(r, c)
            self._update_status()
            return

        # colors set color
        if ch in COLOR_KEYS:
            if self.lock_col[r][c]:
                return
            if self.state[r][c].color_key == ch:
                return
            self._push_undo()
            self.state[r][c].color_key = ch
            self._render_cell(r, c)
            self._update_status()
            return

    # ---------- Render ----------
    def _render_all(self) -> None:
        for r in range(self.R):
            for c in range(self.C):
                self._render_cell(r, c)

    def _render_cell(self, r: int, c: int) -> None:
        st = self.state[r][c]
        lbl = self.cells[r][c]

        bg = CELL_BG_DEFAULT
        if st.color_key:
            bg = COLOR_KEYS[st.color_key]
        lbl.config(bg=bg)

        lbl.config(text="" if st.num is None else str(st.num))
        lbl.config(fg=TEXT_COLOR)

        if self.selected == (r, c):
            lbl.config(highlightthickness=2, highlightbackground=BORDER_SELECTED)
        else:
            lbl.config(highlightthickness=1, highlightbackground=BORDER_NORMAL)

        if self.lock_num[r][c] or self.lock_col[r][c]:
            lbl.config(relief="solid", bd=2)
        else:
            lbl.config(relief="solid", bd=1)

    # ---------- Status ----------
    def _is_complete(self) -> bool:
        for r in range(self.R):
            for c in range(self.C):
                if self.state[r][c].num is None:
                    return False
                if self.state[r][c].color_key is None:
                    return False
        return True

    def _is_correct(self) -> bool:
        for r in range(self.R):
            for c in range(self.C):
                n_truth, col_truth = self.solution[(r, c)]
                st = self.state[r][c]
                if st.num != n_truth:
                    return False
                if st.color_key is None:
                    return False
                if KEY_TO_SOL.get(st.color_key) != col_truth:
                    return False
        return True

    def _update_status(self) -> None:
        if not self._is_complete():
            self.status_label.config(text="Playing", fg=SUM_TEXT_COLOR, bg=self["bg"])
            return

        if self._is_correct():
            self.status_label.config(
                text="Congratulations — you successfully filled this numinous grid!",
                fg=SUM_TEXT_COLOR,
                bg=self["bg"],
            )
        else:
            self.status_label.config(text="Incorrect", fg=SUM_TEXT_COLOR, bg=self["bg"])


def launch_play_editor(puzzle: Puzzle, solution: Dict[Coord, Val]) -> None:
    app = PlayEditor(puzzle=puzzle, solution=solution)
    app.mainloop()


class Launcher(tk.Tk):
    """
    In-game prompt window with Style + Difficulty.
    """

    def __init__(self):
        super().__init__()
        self.title("Numino — New Puzzle")

        self.var_rows = tk.StringVar(value="5")
        self.var_cols = tk.StringVar(value="5")
        self.var_colors = tk.StringVar(value="r y b")
        self.var_numbers = tk.StringVar(value="1 2 3 4 5")
        self.var_style = tk.StringVar(value="BALANCED")
        self.var_difficulty = tk.StringVar(value="HARD")
        self.var_seed = tk.StringVar(value="")

        frm = tk.Frame(self, padx=16, pady=16)
        frm.pack()

        def row(label: str, var: tk.StringVar):
            f = tk.Frame(frm)
            f.pack(fill="x", pady=4)
            tk.Label(f, text=label, width=20, anchor="w").pack(side="left")
            tk.Entry(f, textvariable=var, width=28).pack(side="left")

        row("Rows", self.var_rows)
        row("Cols", self.var_cols)
        row("Colors (r y b g o)", self.var_colors)
        row("Numbers (e.g. 1 2 3)", self.var_numbers)
        row("Style", self.var_style)
        row("Difficulty", self.var_difficulty)
        row("Seed (optional)", self.var_seed)

        tk.Label(frm, text="Style: BALANCED | SMALL_BLOCKY | LARGE_BLOCKY | UNIFORM",
                 fg="#bbbbbb").pack(pady=(6, 0))

        self.msg = tk.Label(frm, text="", fg="#ffaaaa")
        self.msg.pack(pady=(6, 0))

        btn = tk.Button(frm, text="Start", command=self._start)
        btn.pack(pady=(10, 0))

    def _start(self):
        try:
            rows = int(self.var_rows.get().strip())
            cols = int(self.var_cols.get().strip())
            palette = _parse_color_keys(self.var_colors.get())
            numbers = _parse_numbers(self.var_numbers.get())
            style = _parse_style(self.var_style.get())
            difficulty = (self.var_difficulty.get().strip().upper() or "HARD")
            seed_txt = self.var_seed.get().strip()
            seed = int(seed_txt) if seed_txt else _default_seed_timestamp_seconds()

            cfg = ConstructConfig(
                rows=rows,
                cols=cols,
                palette=palette,
                numbers=numbers,
                seed=seed,
                style=style,
                require_all_numbers=True,
                require_all_colors=True,
                max_attempts=200,
            )
            sol, base_puzzle = construct_solution(cfg)

            dcfg = DeconstructConfig(
                seed=seed + 1,
                difficulty=difficulty,
                max_steps=50_000,
                strategy="any",
            )
            stepper = DeconstructorStepper(base_puzzle=base_puzzle, solution=sol, cfg=dcfg)
            puzzle = stepper.run_to_target()

            self.destroy()
            launch_play_editor(puzzle=puzzle, solution=sol)

        except Exception as e:
            self.msg.config(text=str(e))


def launch_app():
    Launcher().mainloop()