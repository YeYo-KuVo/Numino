import tkinter as tk
from dataclasses import dataclass
from typing import List, Set, Dict, Callable, Optional, Tuple
from datetime import datetime


# =========================
# Visual palette (final)
# Codes: B,R,Y,V,P,G  (V=green, G=gray)
# =========================
COLOR_ORDER = ["B", "R", "Y", "V", "P", "G"]
COLOR_HEX = {
    "B": "#6f8ea8",  # blue-gray
    "R": "#b96b5f",  # muted red
    "Y": "#e6cf6a",  # muted yellow
    "V": "#9bb36c",  # green (verde)
    "P": "#9b8cc0",  # purple
    "G": "#8a8a8a",  # gray
}

ROW_COL_OPTIONS = list(range(3, 10))  # 3..9
NUMBER_OPTIONS = list(range(1, 10))   # 1..9
BALANCE_OPTIONS = ["SMALL", "BALANCED", "BIG"]

GLOBAL_MAX_COLORS = 6


def default_seed_timestamp_seconds() -> int:
    return int(datetime.now().strftime("%Y%m%d%H%M%S"))


# =========================
# Cascading rules
# =========================
def max_number_allowed(rows: int, cols: int) -> int:
    """
    Simple rule:
      - Numbers 8 and 9 unlock only on large boards:
          min_dim >= 5 AND area >= 49
      - Otherwise cap at 7 (UI shows 1..9 but 8/9 become X).
    """
    A = rows * cols
    min_dim = min(rows, cols)

    if (min_dim >= 5) and (A >= 49):
        return 9
    return 7


def max_distinct_numbers_allowed(A: int) -> int:
    if A <= 9:
        return 2
    if A <= 16:
        return 3
    if A <= 25:
        return 5
    if A <= 36:
        return 6
    return 7


def max_colors_allowed(A: int, min_dim: int) -> int:
    """
    Relaxed area-based unlocks for max selectable colors:
      - min_dim <= 3: cap at 3
      - A <= 16: 3
      - A < 36: 3
      - A < 64: 4
      - A >= 64: 6
    """
    if min_dim <= 3:
        return min(GLOBAL_MAX_COLORS, 3)

    if A <= 16:
        return min(GLOBAL_MAX_COLORS, 3)
    if A < 36:
        return min(GLOBAL_MAX_COLORS, 3)
    if A < 64:
        return min(GLOBAL_MAX_COLORS, 4)
    return min(GLOBAL_MAX_COLORS, 6)


def balance_availability(rows: int, cols: int, nums: List[int]) -> Dict[str, bool]:
    """
    Relaxed bias rules:
      - BALANCED is always available (handled in UI).
      - SMALL enabled if: n_min <= 2 AND range >= 2
      - BIG enabled if: n_max >= 4 AND area >= 16 AND range >= 2
      - If range < 2 => both SMALL and BIG disabled (Balanced-only feel).
    """
    A = rows * cols
    if not nums:
        return {"SMALL": False, "BIG": False}

    n_min = min(nums)
    n_max = max(nums)
    rng_width = n_max - n_min

    if rng_width < 2:
        return {"SMALL": False, "BIG": False}

    small_ok = (n_min <= 2)
    big_ok = (A >= 16) and (n_max >= 4)
    return {"SMALL": small_ok, "BIG": big_ok}


# =========================
# Result object
# =========================
@dataclass
class CalibrationResult:
    rows: int
    cols: int
    numbers: List[int]
    colors: List[str]
    balance: str
    seed: int


# =========================
# UI Widgets
# =========================
class CircleButton(tk.Canvas):
    """
    Three states:
      - selected: filled circle with white text
      - available: outline circle with dark text
      - disabled: outline with X
    """
    def __init__(self, master, label: str, on_click: Callable[[], None], size=46):
        super().__init__(master, width=size, height=size, highlightthickness=0, bg=master["bg"])
        self.size = size
        self.label = label
        self.on_click = on_click

        self.enabled = True
        self.selected = False
        self._draw()

        self.bind("<Button-1>", self._click)

    def _click(self, _e):
        if not self.enabled:
            return
        self.on_click()

    def set_state(self, enabled: bool, selected: bool, show_x: bool = False):
        self.enabled = enabled
        self.selected = selected
        self.show_x = show_x
        self._draw()

    def _draw(self):
        self.delete("all")
        pad = 5
        r = self.size - pad
        cx = cy = self.size / 2

        if not getattr(self, "enabled", True):
            # disabled
            self.create_oval(pad, pad, r, r, outline="#aaaaaa", width=2)
            self.create_text(cx, cy, text="X", fill="#888888", font=("Helvetica", 16, "bold"))
            return

        if getattr(self, "selected", False):
            self.create_oval(pad, pad, r, r, outline="#555555", width=2, fill="#666666")
            self.create_text(cx, cy, text=self.label, fill="#ffffff", font=("Helvetica", 16, "bold"))
        else:
            self.create_oval(pad, pad, r, r, outline="#888888", width=2, fill="#ffffff")
            self.create_text(cx, cy, text=self.label, fill="#444444", font=("Helvetica", 16, "bold"))


class ColorSwatch(tk.Canvas):
    """
    Three states:
      - selected: shadow under swatch
      - available: no shadow
      - disabled: swatch with X overlay
    """
    def __init__(self, master, code: str, on_click: Callable[[], None], size=46):
        super().__init__(master, width=size, height=size, highlightthickness=0, bg=master["bg"])
        self.size = size
        self.code = code
        self.on_click = on_click

        self.enabled = True
        self.selected = False
        self._draw()

        self.bind("<Button-1>", self._click)

    def _click(self, _e):
        if not self.enabled:
            return
        self.on_click()

    def set_state(self, enabled: bool, selected: bool):
        self.enabled = enabled
        self.selected = selected
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self.size
        col = COLOR_HEX[self.code]

        # Shadow if selected
        if self.enabled and self.selected:
            self.create_rectangle(6, 34, s-6, s-6, fill="#000000", outline="", stipple="gray50")

        # Main square
        self.create_rectangle(6, 6, s-6, s-6, fill=col, outline="#ffffff", width=1)

        if not self.enabled:
            cx = cy = s/2
            self.create_text(cx, cy, text="X", fill="#ffffff", font=("Helvetica", 18, "bold"))


# --- BalanceCircle widget ---
class BalanceCircle(tk.Canvas):
    """
    Three states:
      - selected: filled dark circle with white label
      - available: white circle with gray outline + gray label
      - disabled: white circle with light gray outline + light gray label
    """
    def __init__(self, master, label: str, on_click: Callable[[], None], size: int = 86):
        super().__init__(master, width=size, height=size, highlightthickness=0, bg=master["bg"])
        self.size = size
        self.label = label
        self.on_click = on_click
        self.enabled = True
        self.selected = False
        self._draw()
        self.bind("<Button-1>", self._click)

    def _click(self, _e):
        if not self.enabled:
            return
        self.on_click()

    def set_state(self, enabled: bool, selected: bool):
        self.enabled = enabled
        self.selected = selected
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self.size
        pad = 10
        x0, y0, x1, y1 = pad, pad, s - pad, s - pad
        cx, cy = s / 2, s / 2

        if not self.enabled:
            outline = "#cccccc"
            fill = "#ffffff"
            textc = "#cccccc"
        elif self.selected:
            outline = "#666666"
            fill = "#666666"
            textc = "#ffffff"
        else:
            outline = "#9a9a9a"
            fill = "#ffffff"
            textc = "#666666"

        self.create_oval(x0, y0, x1, y1, outline=outline, width=2, fill=fill)
        self.create_text(cx, cy, text=self.label, fill=textc, font=("Helvetica", 12, "bold"))


class BalanceIcon(tk.Canvas):
    """
    Simple icon placeholder (we can swap for real icons later):
      - selected: darker circle
      - available: outline
      - disabled: faded
    """
    def __init__(self, master, label: str, on_click: Callable[[], None], size=64):
        super().__init__(master, width=size, height=size, highlightthickness=0, bg=master["bg"])
        self.size = size
        self.label = label
        self.on_click = on_click

        self.enabled = True
        self.selected = False
        self._draw()
        self.bind("<Button-1>", self._click)

    def _click(self, _e):
        if not self.enabled:
            return
        self.on_click()

    def set_state(self, enabled: bool, selected: bool):
        self.enabled = enabled
        self.selected = selected
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self.size
        cx = cy = s/2

        if not self.enabled:
            self.create_oval(10, 10, s-10, s-10, outline="#777777", width=2)
            self.create_text(cx, cy, text=self.label[0], fill="#777777", font=("Helvetica", 18, "bold"))
            return

        if self.selected:
            self.create_oval(10, 10, s-10, s-10, outline="#ffffff", width=2, fill="#666666")
            self.create_text(cx, cy, text=self.label[0], fill="#ffffff", font=("Helvetica", 18, "bold"))
        else:
            self.create_oval(10, 10, s-10, s-10, outline="#cccccc", width=2)
            self.create_text(cx, cy, text=self.label[0], fill="#cccccc", font=("Helvetica", 18, "bold"))


# =========================
# Calibrator UI
# =========================
class CalibrationUI(tk.Tk):
    def __init__(self, on_start: Callable[[CalibrationResult], None]):
        super().__init__()
        self.configure(bg="#f6f6f6")
        self.title("Numino — Calibrate")

        self.on_start = on_start

        self.rows = 5
        self.cols = 5

        # Tk variables for the radio strips (so the radios render/track selection correctly)
        self.var_rows = tk.IntVar(value=self.rows)
        self.var_cols = tk.IntVar(value=self.cols)

        # Radio styling (fix: prevent white-on-white)
        self.radio_bg = self["bg"]
        self.radio_fg = "#555555"
        self.radio_active_fg = "#000000"
        self.radio_select = "#ffffff"

        self.selected_numbers: Set[int] = set([1, 2, 3, 4, 5])
        # Start with no colors selected; user chooses up to the cap.
        self.selected_colors: List[str] = []
        self.balance = "BALANCED"

        # Widgets refs
        self.num_btns: Dict[int, CircleButton] = {}
        self.color_btns: Dict[str, ColorSwatch] = {}
        self.balance_btns: Dict[str, BalanceCircle] = {}

        self.status = tk.Label(self, text="", bg=self["bg"], fg="#888888", font=("Helvetica", 11))
        self.start_btn = tk.Button(self, text="▶", font=("Helvetica", 28), command=self._start)

        self._build()
        self._cascade_all()

    def _build(self):
        outer = tk.Frame(self, bg=self["bg"], padx=18, pady=18)
        outer.pack()

        tk.Label(outer, text="NUMINO", bg=self["bg"], fg="#888888", font=("Helvetica", 34)).pack(pady=(0, 12))
        tk.Frame(outer, height=2, bg="#dddddd").pack(fill="x", pady=(0, 18))

        # Rows/Cols selectors as compact “radio strip”
        rc = tk.Frame(outer, bg=self["bg"])
        rc.pack(pady=(0, 18), fill="x")

        tk.Label(rc, text="Rows", bg=self["bg"], fg="#666666", font=("Helvetica", 13, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(rc, text="Cols", bg=self["bg"], fg="#666666", font=("Helvetica", 13, "bold")).grid(row=1, column=0, sticky="w")

        rstrip = tk.Frame(rc, bg=self["bg"])
        cstrip = tk.Frame(rc, bg=self["bg"])
        rstrip.grid(row=0, column=1, sticky="w", padx=(12, 0))
        cstrip.grid(row=1, column=1, sticky="w", padx=(12, 0))

        for v in ROW_COL_OPTIONS:
            tk.Radiobutton(
                rstrip,
                text=str(v),
                variable=self.var_rows,
                value=v,
                indicatoron=True,
                command=lambda vv=v: self._set_rows(vv),
                bg=self.radio_bg,
                fg=self.radio_fg,
                activebackground=self.radio_bg,
                activeforeground=self.radio_active_fg,
                selectcolor=self.radio_select,
                highlightthickness=0,
            ).pack(side="left", padx=4)
        for v in ROW_COL_OPTIONS:
            tk.Radiobutton(
                cstrip,
                text=str(v),
                variable=self.var_cols,
                value=v,
                indicatoron=True,
                command=lambda vv=v: self._set_cols(vv),
                bg=self.radio_bg,
                fg=self.radio_fg,
                activebackground=self.radio_bg,
                activeforeground=self.radio_active_fg,
                selectcolor=self.radio_select,
                highlightthickness=0,
            ).pack(side="left", padx=4)

        # Numbers row
        tk.Label(outer, text="", bg=self["bg"]).pack(pady=(0, 6))
        nums_row = tk.Frame(outer, bg=self["bg"])
        nums_row.pack(pady=(0, 18))

        for n in NUMBER_OPTIONS:
            btn = CircleButton(nums_row, label=str(n), on_click=lambda nn=n: self._toggle_number(nn))
            btn.pack(side="left", padx=6)
            self.num_btns[n] = btn

        # Colors row
        cols_row = tk.Frame(outer, bg=self["bg"])
        cols_row.pack(pady=(0, 22))

        for code in COLOR_ORDER:
            sw = ColorSwatch(cols_row, code=code, on_click=lambda cc=code: self._toggle_color(cc))
            sw.pack(side="left", padx=10)
            self.color_btns[code] = sw

        # Balance row (circular buttons like the mock)
        bal_row = tk.Frame(outer, bg=self["bg"])
        bal_row.pack(pady=(0, 18))

        label_map = {"SMALL": "Small", "BALANCED": "Balanced", "BIG": "Big"}
        for opt in BALANCE_OPTIONS:
            w = BalanceCircle(bal_row, label=label_map[opt], on_click=lambda oo=opt: self._set_balance(oo), size=86)
            w.pack(side="left", padx=26)
            self.balance_btns[opt] = w

        self.status.pack(pady=(8, 10))
        self.start_btn.pack(pady=(6, 0))

    # ---- rows/cols ----
    def _set_rows(self, v: int):
        self.rows = v
        self.var_rows.set(v)
        self._cascade_all()

    def _set_cols(self, v: int):
        self.cols = v
        self.var_cols.set(v)
        self._cascade_all()

    # ---- numbers ----
    def _toggle_number(self, n: int):
        if n not in self.num_btns:
            return
        # ignore disabled
        if not self.num_btns[n].enabled:
            return

        A = self.rows * self.cols
        cap = max_distinct_numbers_allowed(A)

        if n in self.selected_numbers:
            self.selected_numbers.remove(n)
        else:
            if len(self.selected_numbers) >= cap:
                return
            self.selected_numbers.add(n)

        self._cascade_all()

    # ---- colors ----
    def _toggle_color(self, c: str):
        # ignore disabled
        if not self.color_btns[c].enabled:
            return

        A = self.rows * self.cols
        min_dim = min(self.rows, self.cols)
        cap = max_colors_allowed(A, min_dim)

        if c in self.selected_colors:
            self.selected_colors.remove(c)
        else:
            # Enforce cap: require user to deselect one before selecting another.
            if len(self.selected_colors) >= cap:
                return
            self.selected_colors.append(c)

        self._cascade_all()

    # ---- balance ----
    def _set_balance(self, opt: str):
        # Ignore clicks if disabled
        if not self.balance_btns[opt].enabled:
            return
        self.balance = opt
        self._render_balance()

    # ---- cascade ----
    def _effective_numbers(self) -> List[int]:
        if self.selected_numbers:
            return sorted(self.selected_numbers)
        return [1, 2, 3]

    def _cascade_all(self):
        rows, cols = self.rows, self.cols
        A = rows * cols
        min_dim = min(rows, cols)

        # numbers allowed
        maxN = max_number_allowed(rows, cols)
        allowed_numbers = set(range(1, maxN + 1))

        # clamp selection
        self.selected_numbers = {n for n in self.selected_numbers if n in allowed_numbers}

        # enforce distinct cap
        capN = max_distinct_numbers_allowed(A)
        if len(self.selected_numbers) > capN:
            self.selected_numbers = set(sorted(self.selected_numbers)[:capN])

        # colors cap (user may choose ANY colors, up to the cap)
        col_cap = max_colors_allowed(A, min_dim)

        # Clamp selection to known palette codes and to cap
        self.selected_colors = [c for c in self.selected_colors if c in COLOR_ORDER]
        if len(self.selected_colors) > col_cap:
            self.selected_colors = self.selected_colors[:col_cap]

        # balance availability
        nums = self._effective_numbers()
        bal_ok = balance_availability(rows, cols, nums)

        # render everything
        for n, btn in self.num_btns.items():
            enabled = (n in allowed_numbers)
            selected = (n in self.selected_numbers)
            btn.set_state(enabled=enabled, selected=selected)

        # Color swatches: always show all colors. If cap reached, disable unselected swatches (they show "X").
        cap_reached = (len(self.selected_colors) >= col_cap)
        for code, sw in self.color_btns.items():
            selected = (code in self.selected_colors)
            enabled = selected or (not cap_reached)
            sw.set_state(enabled=enabled, selected=selected)

        # Balance widgets: enable/disable + selected styling
        self.balance_btns["BALANCED"].set_state(enabled=True, selected=(self.balance == "BALANCED"))
        self.balance_btns["SMALL"].set_state(enabled=bal_ok["SMALL"], selected=(self.balance == "SMALL"))
        self.balance_btns["BIG"].set_state(enabled=bal_ok["BIG"], selected=(self.balance == "BIG"))

        # clamp invalid chosen balance
        if self.balance == "SMALL" and not bal_ok["SMALL"]:
            self.balance = "BALANCED"
        if self.balance == "BIG" and not bal_ok["BIG"]:
            self.balance = "BALANCED"

        # re-apply selected styling after clamping
        self.balance_btns["BALANCED"].set_state(enabled=True, selected=(self.balance == "BALANCED"))
        self.balance_btns["SMALL"].set_state(enabled=bal_ok["SMALL"], selected=(self.balance == "SMALL"))
        self.balance_btns["BIG"].set_state(enabled=bal_ok["BIG"], selected=(self.balance == "BIG"))

        # start button gating
        start_ok = True
        if not self.selected_numbers:
            start_ok = False
        if sum(self.selected_numbers) > A:
            start_ok = False
        if not self.selected_colors:
            start_ok = False

        self.start_btn.config(state=("normal" if start_ok else "disabled"))

        # status line (debug-friendly)
        self.status.config(
            text=f"Area={A} | min_dim={min_dim} | maxN={maxN} | nums={sorted(self.selected_numbers)} | colors={self.selected_colors} | bias={self.balance}"
        )

    def _render_balance(self):
        # Balance rendering handled by BalanceCircle.set_state in _cascade_all
        return

    # ---- start ----
    def _start(self):
        rows, cols = self.rows, self.cols
        A = rows * cols

        seed = default_seed_timestamp_seconds()

        result = CalibrationResult(
            rows=rows,
            cols=cols,
            numbers=sorted(self.selected_numbers),
            colors=list(self.selected_colors),
            balance=self.balance,
            seed=seed
        )

        self.destroy()
        self.on_start(result)