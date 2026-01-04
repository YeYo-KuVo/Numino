import tkinter as tk
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Callable

from solver import Puzzle, Coord, Val
from calibration import CalibrationUI, CalibrationResult
from constructor import ConstructConfig, construct_solution
from deconstructor import DeconstructConfig, DeconstructorStepper


# =========================
# Visual theme / colors
# =========================
BG = "#2b2b2b"
SUM_TEXT = "#f1f3f5"
TEXT_BLACK = "#000000"

CELL_BG_DEFAULT = "#ffffff"
BORDER_SELECTED = "#ffffff"
BORDER_NORMAL = "#cccccc"

# Final palette (6 colors like your mock):
# Blue, Red, Yellow, Green, Purple, Gray
# Codes: B, R, Y, V (verde), P, G (gray)
COLOR_HEX = {
    "B": "#6f8ea8",  # blue-gray
    "R": "#b96b5f",  # muted red
    "Y": "#e6cf6a",  # muted yellow
    "V": "#9bb36c",  # green (verde)
    "P": "#9b8cc0",  # purple
    "G": "#8a8a8a",  # gray
    # compatibility (if old puzzles still output these)
    "O": "#ffa94d",  # orange
}

PALETTE_ORDER = ["B", "R", "Y", "V", "P", "G"]

# Keyboard hint text (no letters for color, but we show label)
COLOR_KEY_HINT = "Colors (tap swatch; numbers can be typed 0–9)"

SHOW_SOLUTION_REFERENCE = True  # set False when sharing with testers


# =========================
# Play UI
# =========================
@dataclass
class CellState:
    num: Optional[int] = None
    col: Optional[str] = None  # one of palette codes (e.g., "B","R","Y","V","P","G") or None


class PlayEditor(tk.Tk):
    """
    Mobile-style interaction:
      - Select ONE tool (number OR color) from palettes
      - Click cell to apply tool
      - Disabled palette items show "X"
      - Keyboard digits select number tool

    Includes:
      - Undo (multi-step)
      - Reset
      - Auto-check on completion
    """

    def __init__(self, puzzle: Puzzle, solution: Dict[Coord, Val], bias_label: str, puzzle_id: str):
        super().__init__()
        self.configure(bg=BG)
        self.title("Numino — Play")

        self.puzzle = puzzle
        self.solution = solution
        self.bias_label = bias_label  # "SMALL" / "BALANCED" / "BIG"
        self.puzzle_id = puzzle_id

        self.R = puzzle.rows
        self.C = puzzle.cols

        # Allowed sets from puzzle definition
        self.allowed_numbers = set(puzzle.numbers)
        self.allowed_colors = set(puzzle.palette)

        # Givens map (r,c)->(num?, col?)
        self.givens_map: Dict[Tuple[int, int], Tuple[Optional[int], Optional[str]]] = {}
        for g in puzzle.givens:
            self.givens_map[(g.r, g.c)] = (g.num, g.col)

        # Locks per cell
        self.lock_num = [[False] * self.C for _ in range(self.R)]
        self.lock_col = [[False] * self.C for _ in range(self.R)]
        for (r, c), (n, col) in self.givens_map.items():
            if n is not None:
                self.lock_num[r][c] = True
            if col is not None:
                self.lock_col[r][c] = True

        # Player state starts with givens
        self.state: List[List[CellState]] = [[CellState() for _ in range(self.C)] for _ in range(self.R)]
        for r in range(self.R):
            for c in range(self.C):
                n, col = self.givens_map.get((r, c), (None, None))
                self.state[r][c].num = n
                self.state[r][c].col = col

        # Undo
        self.initial_state = self._snapshot_state()
        self.undo_stack: List[List[List[Tuple[Optional[int], Optional[str]]]]] = []
        # Optional checkpoint: when set, Undo cannot go earlier than this snapshot.
        # Implementation: locking saves a snapshot and clears undo history so the earliest reachable state becomes the lock.
        self.lock_state: Optional[List[List[Tuple[Optional[int], Optional[str]]]]] = None

        # Selection
        self.selected_cell: Optional[Tuple[int, int]] = None

        # Active tool (exclusive)
        self.active_tool_type: Optional[str] = None  # "num" | "col" | None
        self.active_tool_value: Optional[object] = None  # int for num, str for col, or None for clears

        # UI refs
        self.cells: List[List[tk.Label]] = []
        self.status_label: Optional[tk.Label] = None
        self.undo_btn: Optional[tk.Button] = None
        self.lock_btn: Optional[tk.Button] = None
        self.lock_status_lbl: Optional[tk.Label] = None

        self.num_tool_btns: Dict[int, tk.Button] = {}   # 0..9 (0 clears number)
        self.col_tool_btns: Dict[str, tk.Button] = {}   # palette codes + "CLEAR"

        self._build_ui()
        self._render_all()
        self._update_status()
        self._update_undo_button()
        self._update_tool_highlights()
        if SHOW_SOLUTION_REFERENCE:
            self._open_solution_reference_window()

        # Key bindings
        self.bind("<Escape>", self._clear_tool)
        self.bind("<Delete>", self._on_delete_color)
        self.bind("<BackSpace>", self._on_delete_color)
        self.bind_all("<Command-z>", self._on_undo)
        self.bind_all("<Control-z>", self._on_undo)

        # Keyboard numbers select number tool (0 clears number)
        self.bind("<KeyPress>", self._on_keypress)

        self.focus_force()

    # ---------- snapshots / undo ----------
    def _snapshot_state(self) -> List[List[Tuple[Optional[int], Optional[str]]]]:
        snap = []
        for r in range(self.R):
            row = []
            for c in range(self.C):
                st = self.state[r][c]
                row.append((st.num, st.col))
            snap.append(row)
        return snap

    def _restore_snapshot(self, snap: List[List[Tuple[Optional[int], Optional[str]]]]) -> None:
        for r in range(self.R):
            for c in range(self.C):
                n, col = snap[r][c]
                self.state[r][c].num = n
                self.state[r][c].col = col

    def _push_undo(self) -> None:
        self.undo_stack.append(self._snapshot_state())
        self._update_undo_button()

    def _update_undo_button(self) -> None:
        if self.undo_btn is None:
            return
        self.undo_btn.config(state=("normal" if self.undo_stack else "disabled"))

    def _update_lock_ui(self) -> None:
        if self.lock_btn is not None:
            # Show whether a checkpoint exists
            self.lock_btn.config(text=("Unlock" if self.lock_state is not None else "Lock"))
        if self.lock_status_lbl is not None:
            self.lock_status_lbl.config(text=("🔒 Locked" if self.lock_state is not None else ""))

    def _on_lock(self) -> None:
        # Toggle lock: if currently unlocked, create checkpoint; if locked, clear checkpoint.
        if self.lock_state is None:
            self.lock_state = self._snapshot_state()
            # Clear undo history so user can only undo back to this checkpoint
            self.undo_stack.clear()
        else:
            # Unlock returns to normal undo behavior (still limited by available history)
            self.lock_state = None
        self._update_undo_button()
        self._update_lock_ui()
        self._update_status()

    def _on_undo(self, _event=None) -> None:
        if not self.undo_stack:
            return
        snap = self.undo_stack.pop()
        self._restore_snapshot(snap)
        self.selected_cell = None
        self._render_all()
        self._update_status()
        self._update_undo_button()
        self._update_lock_ui()

    # ---------- tool handling ----------
    def _set_num_tool(self, n: int) -> None:
        # allow selecting even if not allowed? as instrument, show X for disabled; clicking does nothing.
        if n != 0 and n not in self.allowed_numbers:
            return
        self.active_tool_type = "num"
        self.active_tool_value = n  # 0 means clear number
        self._update_tool_highlights()

    def _set_color_tool(self, code: str) -> None:
        # code can be "CLEAR" or a color code like "B"
        if code != "CLEAR" and code not in self.allowed_colors:
            return
        self.active_tool_type = "col"
        self.active_tool_value = code
        self._update_tool_highlights()

    def _clear_tool(self, _event=None) -> None:
        self.active_tool_type = None
        self.active_tool_value = None
        self._update_tool_highlights()

    def _update_tool_highlights(self) -> None:
        # Number tools
        for n, btn in self.num_tool_btns.items():
            active = (self.active_tool_type == "num" and self.active_tool_value == n)
            btn.config(relief=("sunken" if active else "raised"))

        # Color tools
        for code, btn in self.col_tool_btns.items():
            active = (self.active_tool_type == "col" and self.active_tool_value == code)
            btn.config(relief=("sunken" if active else "raised"))

        # Also refresh status line (shows tool)
        self._update_status()

    # ---------- applying tools ----------
    def _apply_tool_to_cell(self, r: int, c: int) -> None:
        if self.active_tool_type is None:
            return  # no tool selected; just selection highlight

        st = self.state[r][c]
        changed = False

        # Apply number tool
        if self.active_tool_type == "num":
            n = int(self.active_tool_value)
            if self.lock_num[r][c]:
                return
            new_num = None if n == 0 else n
            if st.num != new_num:
                self._push_undo()
                st.num = new_num
                changed = True

        # Apply color tool
        elif self.active_tool_type == "col":
            code = str(self.active_tool_value)
            if self.lock_col[r][c]:
                return
            new_col = None if code == "CLEAR" else code
            if st.col != new_col:
                self._push_undo()
                st.col = new_col
                changed = True

        if changed:
            self._render_cell(r, c)
            self._update_status()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        outer = tk.Frame(self, padx=14, pady=14, bg=BG)
        outer.pack()

        # Top bar: Undo / Reset + metadata
        topbar = tk.Frame(outer, bg=BG)
        topbar.pack(fill="x", pady=(0, 8))

        self.undo_btn = tk.Button(topbar, text="Undo", command=self._on_undo)
        self.undo_btn.pack(side="left", padx=(0, 8))

        self.lock_btn = tk.Button(topbar, text="Lock", command=self._on_lock)
        self.lock_btn.pack(side="left", padx=(0, 8))

        tk.Button(topbar, text="Reset", command=self._on_reset).pack(side="left")

        # Lock indicator (shows when a checkpoint is set)
        self.lock_status_lbl = tk.Label(topbar, text="", fg=SUM_TEXT, bg=BG, font=("Helvetica", 12, "bold"))
        self.lock_status_lbl.pack(side="left", padx=(12, 0))

        # Meta info (numbers/colors/bias)
        allowed_nums = " ".join(map(str, sorted(self.allowed_numbers)))
        allowed_cols = " ".join(sorted(self.allowed_colors))
        meta = tk.Label(
            outer,
            text=f"ID: {self.puzzle_id}\nNumbers: {allowed_nums}   |   Colors: {allowed_cols}   |   Bias: {self.bias_label}",
            fg=SUM_TEXT,
            bg=BG,
            font=("Helvetica", 12, "bold"),
            pady=6,
        )
        meta.pack()

        # Grid with sums
        frame = tk.Frame(outer, bg=BG)
        frame.pack(pady=(6, 10))

        tk.Label(frame, text="", width=4, height=2, bg=BG).grid(row=0, column=0)

        # Column sums (top)
        for c in range(self.C):
            tk.Label(
                frame,
                text=str(self.puzzle.col_sums[c]),
                width=4,
                height=2,
                font=("Helvetica", 12, "bold"),
                fg=SUM_TEXT,
                bg=BG,
            ).grid(row=0, column=c + 1, padx=1, pady=1)

        # Rows + cells
        self.cells = []
        for r in range(self.R):
            tk.Label(
                frame,
                text=str(self.puzzle.row_sums[r]),
                width=4,
                height=2,
                font=("Helvetica", 12, "bold"),
                fg=SUM_TEXT,
                bg=BG,
            ).grid(row=r + 1, column=self.C + 1, padx=1, pady=1)

            row_widgets: List[tk.Label] = []
            for c in range(self.C):
                lbl = tk.Label(
                    frame,
                    text="",
                    width=4,
                    height=2,
                    bg=CELL_BG_DEFAULT,
                    fg=TEXT_BLACK,
                    relief="solid",
                    bd=1,
                    font=("Helvetica", 16, "bold"),
                    highlightthickness=1,
                    highlightbackground=BORDER_NORMAL,
                )
                lbl.grid(row=r + 1, column=c + 1, padx=1, pady=1, sticky="nsew")
                lbl.bind("<Button-1>", lambda e, rr=r, cc=c: self._on_cell_click(rr, cc))
                row_widgets.append(lbl)
            self.cells.append(row_widgets)

        # Status line
        self.status_label = tk.Label(
            self,
            text="",
            padx=12,
            pady=10,
            font=("Helvetica", 16, "bold"),
            bg=BG,
            fg=SUM_TEXT,
        )
        self.status_label.pack()

        # Tool palettes
        palette_frame = tk.Frame(outer, bg=BG)
        palette_frame.pack(pady=(10, 0), fill="x")

        # Numbers palette (0-9 in two rows like mock)
        tk.Label(palette_frame, text="Numbers", fg=SUM_TEXT, bg=BG, font=("Helvetica", 12, "bold")).pack(anchor="w")

        nums_grid = tk.Frame(palette_frame, bg=BG)
        nums_grid.pack(pady=(4, 10))

        number_layout = [
            [0, 1, 2, 3, 4, 5],
            [6, 7, 8, 9, None, None],
        ]
        for rr, row in enumerate(number_layout):
            for cc, n in enumerate(row):
                if n is None:
                    tk.Label(nums_grid, text="", width=4, bg=BG).grid(row=rr, column=cc, padx=6, pady=4)
                    continue

                allowed = (n == 0) or (n in self.allowed_numbers)
                text = str(n) if allowed else "X"
                btn = tk.Button(nums_grid, text=text, width=4, command=lambda nn=n: self._set_num_tool(nn))
                btn.grid(row=rr, column=cc, padx=6, pady=4)
                if not allowed:
                    btn.config(state="disabled")
                self.num_tool_btns[n] = btn

        # Colors palette
        tk.Label(palette_frame, text=COLOR_KEY_HINT, fg=SUM_TEXT, bg=BG, font=("Helvetica", 12, "bold")).pack(anchor="w")

        cols_row = tk.Frame(palette_frame, bg=BG)
        cols_row.pack(pady=(4, 4))

        clear_btn = tk.Button(cols_row, text="", width=4, command=lambda: self._set_color_tool("CLEAR"))
        clear_btn.pack(side="left", padx=6)
        self.col_tool_btns["CLEAR"] = clear_btn

        for code in PALETTE_ORDER:
            allowed = (code in self.allowed_colors)
            text = code if allowed else "X"
            btn = tk.Button(cols_row, text=text, width=4, command=lambda cc=code: self._set_color_tool(cc))
            btn.pack(side="left", padx=6)
            if code in COLOR_HEX:
                btn.config(bg=COLOR_HEX[code])
            if not allowed:
                btn.config(state="disabled")
            self.col_tool_btns[code] = btn

        tk.Label(
            palette_frame,
            text="Tip: select a tool, then click a cell. Esc clears tool selection.",
            fg="#bbbbbb",
            bg=BG
        ).pack(pady=(6, 0))

        self._update_lock_ui()

    def _open_solution_reference_window(self) -> None:
        win = tk.Toplevel(self)
        win.title("Numino — Solution Reference")
        win.configure(bg=BG)

        outer = tk.Frame(win, padx=14, pady=14, bg=BG)
        outer.pack()

        # Header mirrors play UI
        allowed_nums = " ".join(map(str, sorted(self.allowed_numbers)))
        allowed_cols = " ".join(sorted(self.allowed_colors))
        meta = tk.Label(
            outer,
            text=(
                f"SOLUTION (Reference)\n"
                f"ID: {self.puzzle_id}\n"
                f"Numbers: {allowed_nums}   |   Colors: {allowed_cols}   |   Bias: {self.bias_label}"
            ),
            fg=SUM_TEXT,
            bg=BG,
            font=("Helvetica", 12, "bold"),
            pady=6,
            justify="center",
        )
        meta.pack()

        # Grid with sums (same visual language as play UI)
        frame = tk.Frame(outer, bg=BG)
        frame.pack(pady=(6, 10))

        tk.Label(frame, text="", width=4, height=2, bg=BG).grid(row=0, column=0)

        # Column sums (top)
        for c in range(self.C):
            tk.Label(
                frame,
                text=str(self.puzzle.col_sums[c]),
                width=4,
                height=2,
                font=("Helvetica", 12, "bold"),
                fg=SUM_TEXT,
                bg=BG,
            ).grid(row=0, column=c + 1, padx=1, pady=1)

        # Rows + solved cells + row sums (right)
        for r in range(self.R):
            tk.Label(
                frame,
                text=str(self.puzzle.row_sums[r]),
                width=4,
                height=2,
                font=("Helvetica", 12, "bold"),
                fg=SUM_TEXT,
                bg=BG,
            ).grid(row=r + 1, column=self.C + 1, padx=1, pady=1)

            for c in range(self.C):
                n, col = self.solution[(r, c)]
                bg = CELL_BG_DEFAULT
                if col and col in COLOR_HEX:
                    bg = COLOR_HEX[col]
                tk.Label(
                    frame,
                    text=str(n),
                    width=4,
                    height=2,
                    bg=bg,
                    fg=TEXT_BLACK,
                    relief="solid",
                    bd=1,
                    font=("Helvetica", 16, "bold"),
                ).grid(row=r + 1, column=c + 1, padx=1, pady=1, sticky="nsew")

        tk.Label(
            outer,
            text="(Read-only) Screenshot this window for your database.",
            fg="#bbbbbb",
            bg=BG,
            pady=6,
        ).pack()

        # Bring solution window to front so it doesn't open behind the play window
        try:
            win.lift()
            win.attributes("-topmost", True)
            win.after(200, lambda: win.attributes("-topmost", False))
        except Exception:
            pass

    # ---------- events ----------
    def _on_cell_click(self, r: int, c: int) -> None:
        # select cell
        prev = self.selected_cell
        self.selected_cell = (r, c)
        if prev is not None:
            self._render_cell(prev[0], prev[1])
        self._render_cell(r, c)

        # apply tool if any
        self._apply_tool_to_cell(r, c)

    def _on_keypress(self, event: tk.Event) -> None:
        ch = (event.char or "").strip()
        if not ch:
            return
        if ch.isdigit():
            self._set_num_tool(int(ch))  # 0 clears number

    def _on_delete_color(self, _event=None) -> None:
        # Treat Delete as selecting CLEAR color tool and applying if cell selected
        if self.selected_cell is None:
            return
        r, c = self.selected_cell
        if self.lock_col[r][c]:
            return
        if self.state[r][c].col is None:
            return
        self._push_undo()
        self.state[r][c].col = None
        self._render_cell(r, c)
        self._update_status()

    def _on_reset(self) -> None:
        self._restore_snapshot(self.initial_state)
        self.undo_stack.clear()
        self.lock_state = None
        self.selected_cell = None
        self._render_all()
        self._update_status()
        self._update_undo_button()
        self._update_lock_ui()

    # ---------- rendering ----------
    def _render_all(self) -> None:
        for r in range(self.R):
            for c in range(self.C):
                self._render_cell(r, c)

    def _render_cell(self, r: int, c: int) -> None:
        st = self.state[r][c]
        lbl = self.cells[r][c]

        bg = CELL_BG_DEFAULT
        if st.col and st.col in COLOR_HEX:
            bg = COLOR_HEX[st.col]
        lbl.config(bg=bg)

        lbl.config(text="" if st.num is None else str(st.num), fg=TEXT_BLACK)

        # selection border
        if self.selected_cell == (r, c):
            lbl.config(highlightthickness=2, highlightbackground=BORDER_SELECTED)
        else:
            lbl.config(highlightthickness=1, highlightbackground=BORDER_NORMAL)

        # givens thicker border
        if self.lock_num[r][c] or self.lock_col[r][c]:
            lbl.config(relief="solid", bd=2)
        else:
            lbl.config(relief="solid", bd=1)

    # ---------- status ----------
    def _is_complete(self) -> bool:
        for r in range(self.R):
            for c in range(self.C):
                if self.state[r][c].num is None:
                    return False
                if self.state[r][c].col is None:
                    return False
        return True

    def _is_correct(self) -> bool:
        for r in range(self.R):
            for c in range(self.C):
                n_truth, col_truth = self.solution[(r, c)]
                st = self.state[r][c]
                if st.num != n_truth:
                    return False
                if st.col != col_truth:
                    return False
        return True

    def _update_status(self) -> None:
        # Show active tool
        tool_txt = "Tool: none"
        if self.active_tool_type == "num":
            n = int(self.active_tool_value)
            tool_txt = f"Tool: number {n}" if n != 0 else "Tool: clear number"
        elif self.active_tool_type == "col":
            code = str(self.active_tool_value)
            tool_txt = "Tool: clear color" if code == "CLEAR" else f"Tool: color {code}"

        if not self._is_complete():
            self.status_label.config(text=f"Playing   |   {tool_txt}")
            return

        if self._is_correct():
            self.status_label.config(text="Congratulations — you successfully filled this numinous grid!")
        else:
            self.status_label.config(text="Incorrect")


def launch_play_editor(puzzle: Puzzle, solution: Dict[Coord, Val], bias_label: str, puzzle_id: str) -> None:
    PlayEditor(puzzle, solution, bias_label, puzzle_id).mainloop()


# =========================
# App entry: calibration -> generate -> play
# =========================
def launch_app():
    def on_start(cfg: CalibrationResult):
        print("PUZZLE_ID:", cfg.seed, cfg.rows, cfg.cols, cfg.numbers, cfg.colors, cfg.balance)

        from tkinter import messagebox

        try:
            puzzle, sol, style, puzzle_id, _difficulty = generate_puzzle_from_calibration(cfg)
        except RuntimeError as e:
            messagebox.showerror("Puzzle generation failed", str(e))
            return

        launch_play_editor(puzzle, sol, bias_label=style, puzzle_id=puzzle_id)

    CalibrationUI(on_start).mainloop()

# =========================
# Puzzle generation (reusable)
# =========================

def generate_puzzle_from_calibration(cfg: CalibrationResult) -> Tuple[Puzzle, Dict[Coord, Val], str, str, str]:
    """
    Runs: calibration -> constructor -> deconstructor.

    Returns:
      - puzzle: the deconstructed (playable) Puzzle
      - sol: full solution dict (r,c)->(num,col)
      - style: bias label ("SMALL"/"BALANCED"/"BIG")
      - puzzle_id: human-readable identifier string
      - difficulty: difficulty label string (e.g. "HARD")

    Raises RuntimeError with a user-friendly message if generation fails.

    NOTE: This function does not open any UI windows; it is safe to call from a CLI exporter.
    """

    # balance maps to constructor style directly ("SMALL"/"BALANCED"/"BIG")
    style = cfg.balance

    MAX_CONSTRUCT_TRIES = 25
    MAX_DECONSTRUCT_TRIES = 10

    c_cfg = ConstructConfig(
        rows=cfg.rows,
        cols=cfg.cols,
        palette=cfg.colors,
        numbers=cfg.numbers,
        seed=cfg.seed,
        style=style,
        require_all_numbers=True,
        require_all_colors=True,
        max_attempts=300,
    )

    # --- constructor retries (vary seed) ---
    sol = None
    base_puzzle = None
    base_seed = cfg.seed
    for i in range(MAX_CONSTRUCT_TRIES):
        try_seed = base_seed + i
        c_cfg.seed = try_seed
        try:
            sol, base_puzzle = construct_solution(c_cfg)
            break
        except RuntimeError:
            continue

    if sol is None or base_puzzle is None:
        raise RuntimeError(
            "Numino couldn't generate a puzzle for this exact configuration.\n\n"
            "Try one of these:\n"
            "• Add a larger number (e.g., include 4 on 4×4)\n"
            "• Increase the grid size\n"
            "• Select more colors (if available)\n"
            "• Use BALANCED for small grids\n"
        )

    difficulty = "HARD"
    d_cfg = DeconstructConfig(
        seed=c_cfg.seed + 1,
        difficulty=difficulty,
        max_steps=50_000,
        strategy="any",
    )

    # --- deconstructor retries (vary seed) ---
    puzzle = None
    for j in range(MAX_DECONSTRUCT_TRIES):
        try:
            d_cfg.seed = (c_cfg.seed + 1) + j
            stepper = DeconstructorStepper(base_puzzle=base_puzzle, solution=sol, cfg=d_cfg)
            puzzle = stepper.run_to_target()
            break
        except RuntimeError:
            continue

    if puzzle is None:
        raise RuntimeError(
            "A solution grid was found, but Numino couldn't deconstruct it into a unique puzzle.\n\n"
            "Try selecting more numbers/colors, or a different grid size."
        )

    puzzle_id = (
        f"{c_cfg.seed} | {cfg.rows}x{cfg.cols} | nums={','.join(map(str, cfg.numbers))} | "
        f"cols={''.join(cfg.colors)} | bias={style}"
    )

    return puzzle, sol, style, puzzle_id, difficulty