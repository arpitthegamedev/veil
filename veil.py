
"""
██╗   ██╗███████╗██╗██╗
██║   ██║██╔════╝██║██║
██║   ██║█████╗  ██║██║
╚██╗ ██╔╝██╔══╝  ██║██║
 ╚████╔╝ ███████╗██║███████╗
  ╚═══╝  ╚══════╝╚═╝╚══════╝

Veil — Stealth Window Killer
Author  : Arpit Kumar Tiwari
Version : 0.2.1 (Visual Overhaul)
Stack   : Python + tkinter + keyboard + win32gui + pystray + PIL
"""

import os
import json
import math
import threading
import subprocess
from datetime import datetime
import tkinter as tk

# ─── Optional imports with graceful fallback ───────────────────────────────────
try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

try:
    import win32gui
    import win32process
    import psutil
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


# ─── Constants ─────────────────────────────────────────────────────────────────

CONFIG_FILE = "veil_config.json"

# Processes Veil will NEVER kill under any circumstance
PROTECTED = {
    "explorer.exe", "python.exe", "pythonw.exe",
    "veil.exe", "cursor.exe", "code.exe",
    "taskmgr.exe", "winlogon.exe", "svchost.exe",
}

# ── Fonts — Consolas is built-in on Windows, much sharper than Courier New ────
FONT_XS    = ("Consolas", 8)
FONT_SM    = ("Consolas", 9)
FONT_MD    = ("Consolas", 10)
FONT_LG    = ("Consolas", 11)
FONT_XL    = ("Consolas", 13, "bold")
FONT_CLOCK = ("Consolas", 18, "bold")
FONT_DATE  = ("Consolas", 9)

# ── Window ────────────────────────────────────────────────────────────────────
WIN_W = 380
WIN_H = 560

# ── Circle geometry ───────────────────────────────────────────────────────────
CIRCLE_D   = 110        # main circle diameter (px)
CANVAS_PAD = 30         # padding around circle inside canvas
CANVAS_SZ  = CIRCLE_D + CANVAS_PAD * 2

# ── Timing ────────────────────────────────────────────────────────────────────
PULSE_MS  = 28          # ms per pulse animation frame
CLOCK_MS  = 1000        # ms per clock update

# ── Theme palettes ─────────────────────────────────────────────────────────────
THEMES = {
    "dark": {
        "bg":          "#0a0a0a",    # main background
        "bg2":         "#111111",    # slightly lighter panel
        "fg":          "#e8e8e8",    # primary text
        "fg_dim":      "#444444",    # dimmed / meta text
        "fg_mid":      "#777777",    # secondary text
        "outline":     "#e8e8e8",    # circle + active elements
        "sep":         "#1c1c1c",    # separator lines
        "tab_bg":      "#0d0d0d",    # tab bar background
        "tab_ln":      "#e8e8e8",    # active tab top line
        "log_alt":     "#0d0d0d",    # alternating log row tint
        "btn_hover":   "#181818",    # clear button hover
    },
    "light": {
        "bg":          "#f7f7f5",
        "bg2":         "#eeeeec",
        "fg":          "#111111",
        "fg_dim":      "#bbbbbb",
        "fg_mid":      "#777777",
        "outline":     "#111111",
        "sep":         "#e2e2e0",
        "tab_bg":      "#efefed",
        "tab_ln":      "#111111",
        "log_alt":     "#ebebea",
        "btn_hover":   "#e5e5e3",
    },
}

# Log row status colors (same in both themes for clarity)
LOG_COLORS = {
    "KILLED":  "#4caf50",
    "SKIPPED": "#e05555",
    "ERROR":   "#666666",
}


# ─── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load persisted config, or return safe defaults."""
    defaults = {"theme": "dark", "armed": False}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                defaults.update(json.load(f))
        except Exception:
            pass
    return defaults


def save_config(data: dict):
    """Write config dict to JSON file."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ─── Process helpers ───────────────────────────────────────────────────────────

def get_foreground_process():
    """Return (process_name, pid) of the focused window. Falls back to ('unknown', -1)."""
    if not HAS_WIN32:
        return ("unknown", -1)
    try:
        hwnd = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return (psutil.Process(pid).name().lower(), pid)
    except Exception:
        return ("unknown", -1)


def kill_pid(pid: int) -> bool:
    """Force-kill a process by PID. Returns True on success."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True, timeout=3,
        )
        return True
    except Exception:
        return False


# ─── Tray icon ────────────────────────────────────────────────────────────────

def make_tray_icon(theme: str):
    """Generate a 64x64 PIL icon with a 'V' glyph."""
    size = 64
    bg   = (10, 10, 10, 255)    if theme == "dark" else (247, 247, 245, 255)
    fg   = (232, 232, 232)       if theme == "dark" else (17, 17, 17)
    img  = Image.new("RGBA", (size, size), bg)
    draw = ImageDraw.Draw(img)
    pts  = [(12, 16), (32, 48), (52, 16), (46, 16), (32, 38), (18, 16)]
    draw.polygon(pts, fill=fg)
    return img


# ─── Main Application ──────────────────────────────────────────────────────────

class VeilApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Veil")
        self.root.resizable(False, False)
        self.root.geometry(f"{WIN_W}x{WIN_H}")

        # ── State ─────────────────────────────────────────────────────────────
        cfg           = load_config()
        self.theme    = cfg.get("theme", "dark")
        self.armed    = cfg.get("armed", False)
        self.log_entries = []       # list of dicts: {time, process, status}
        self.active_tab  = "home"

        # Internal animation / task handles
        self._pulse_angle = 0.0
        self._pulse_job   = None
        self._clock_job   = None
        self._hover       = False
        self._tray_icon   = None

        # ── Build & launch ────────────────────────────────────────────────────
        self._build_ui()
        self._apply_theme(animate=False)
        self._start_clock()
        self._start_hotkey()
        self._start_tray()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(60, self._do_show_window)   # show after first paint

    # ─── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        t = THEMES[self.theme]

        # Root frame fills everything
        self.root_frame = tk.Frame(self.root, bg=t["bg"])
        self.root_frame.pack(fill="both", expand=True)

        # ── Header ────────────────────────────────────────────────────────────
        self.header = tk.Frame(self.root_frame, bg=t["bg"], height=54)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        # Live clock — top left, large
        self.clock_lbl = tk.Label(
            self.header, text="00:00:00",
            font=FONT_CLOCK,
            bg=t["bg"], fg=t["fg"],
            anchor="w",
        )
        self.clock_lbl.place(x=16, rely=0.5, anchor="w")

        # App name — centered, dimmed
        self.title_lbl = tk.Label(
            self.header, text="VEIL",
            font=FONT_XL,
            bg=t["bg"], fg=t["fg_dim"],
        )
        self.title_lbl.place(relx=0.5, rely=0.5, anchor="center")

        # Theme toggle — top right
        self.theme_btn = tk.Label(
            self.header,
            text="☀" if self.theme == "dark" else "☽",
            font=("Consolas", 15),
            bg=t["bg"], fg=t["fg"],
            cursor="hand2",
        )
        self.theme_btn.place(relx=1.0, x=-16, rely=0.5, anchor="e")
        self.theme_btn.bind("<Button-1>", lambda e: self._toggle_theme())
        self.theme_btn.bind("<Enter>",    lambda e: self.theme_btn.config(fg=THEMES[self.theme]["fg_mid"]))
        self.theme_btn.bind("<Leave>",    lambda e: self.theme_btn.config(fg=THEMES[self.theme]["fg"]))

        # Date — below header, right-aligned
        self.date_lbl = tk.Label(
            self.root_frame,
            text="",   # filled by clock tick
            font=FONT_DATE,
            bg=t["bg"], fg=t["fg_dim"],
            anchor="e",
        )
        self.date_lbl.pack(fill="x", padx=16)

        # Thin top separator
        self.sep1 = tk.Frame(self.root_frame, bg=t["sep"], height=1)
        self.sep1.pack(fill="x", pady=(6, 0))

        # ── Main content area (home / log swap here) ───────────────────────────
        self.content = tk.Frame(self.root_frame, bg=t["bg"])
        self.content.pack(fill="both", expand=True)

        self._build_home()
        self._build_log()

        # ── Bottom separator ──────────────────────────────────────────────────
        self.sep2 = tk.Frame(self.root_frame, bg=t["sep"], height=1)
        self.sep2.pack(fill="x")

        # ── Tab bar ───────────────────────────────────────────────────────────
        self.tab_bar = tk.Frame(self.root_frame, bg=t["tab_bg"], height=44)
        self.tab_bar.pack(fill="x")
        self.tab_bar.pack_propagate(False)

        # Vertical divider between tabs
        self.tab_div = tk.Frame(self.tab_bar, bg=t["sep"], width=1)
        self.tab_div.place(relx=0.5, y=0, height=44)

        # Build each tab as a frame with an indicator line + label
        self.tab_home_frm, self.tab_home_lbl, self.tab_home_ind = self._make_tab("HOME",     "home", "left")
        self.tab_log_frm,  self.tab_log_lbl,  self.tab_log_ind  = self._make_tab("KILL LOG", "log",  "right")

        self._update_tabs()
        self._show_home()

    def _make_tab(self, text, name, side):
        """Build a single tab widget with an active-indicator line at top."""
        t   = THEMES[self.theme]
        frm = tk.Frame(self.tab_bar, bg=t["tab_bg"], cursor="hand2")
        frm.pack(side=side, fill="both", expand=True)

        # 2px indicator line at top of tab — highlighted when active
        ind = tk.Frame(frm, height=2, bg=t["tab_bg"])
        ind.pack(fill="x")

        lbl = tk.Label(
            frm, text=text,
            font=FONT_SM,
            bg=t["tab_bg"], fg=t["fg_mid"],
            cursor="hand2",
        )
        lbl.pack(expand=True)

        frm.bind("<Button-1>", lambda e, n=name: self._switch_tab(n))
        lbl.bind("<Button-1>", lambda e, n=name: self._switch_tab(n))
        return frm, lbl, ind

    # ─── Home tab ─────────────────────────────────────────────────────────────

    def _build_home(self):
        t = THEMES[self.theme]
        self.home_frame = tk.Frame(self.content, bg=t["bg"])

        # Upper spacer — pushes circle to upper-center region
        tk.Frame(self.home_frame, bg=t["bg"], height=44).pack()

        # Circle canvas
        self.canvas = tk.Canvas(
            self.home_frame,
            width=CANVAS_SZ, height=CANVAS_SZ,
            bg=t["bg"], highlightthickness=0,
            cursor="hand2",
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_circle_click)
        self.canvas.bind("<Enter>",    lambda e: self._set_hover(True))
        self.canvas.bind("<Leave>",    lambda e: self._set_hover(False))
        self._draw_circle()

        # State label: ARMED / SAFE
        self.state_lbl = tk.Label(
            self.home_frame,
            text="ARMED" if self.armed else "SAFE",
            font=("Consolas", 11, "bold"),
            bg=t["bg"], fg=t["fg"],
        )
        self.state_lbl.pack(pady=(12, 0))

        # Small hint line
        self.hint_lbl = tk.Label(
            self.home_frame,
            text="F8 active" if self.armed else "F8 inactive",
            font=FONT_XS,
            bg=t["bg"], fg=t["fg_dim"],
        )
        self.hint_lbl.pack(pady=(4, 0))

        # Flexible spacer — pushes stats to bottom
        tk.Frame(self.home_frame, bg=t["bg"]).pack(expand=True)

        # Stat strip at bottom of home panel
        self.stat_bar = tk.Frame(self.home_frame, bg=t["bg"])
        self.stat_bar.pack(fill="x", padx=20, pady=(0, 18))

        self.kills_lbl = tk.Label(
            self.stat_bar, text="KILLS  0",
            font=FONT_XS, bg=t["bg"], fg=t["fg_dim"], anchor="w",
        )
        self.kills_lbl.pack(side="left")

        self.skips_lbl = tk.Label(
            self.stat_bar, text="SKIPPED  0",
            font=FONT_XS, bg=t["bg"], fg=t["fg_dim"], anchor="e",
        )
        self.skips_lbl.pack(side="right")

    # ─── Log tab ──────────────────────────────────────────────────────────────

    def _build_log(self):
        t = THEMES[self.theme]
        self.log_frame = tk.Frame(self.content, bg=t["bg"])

        # Column headers
        self.log_hdr = tk.Frame(self.log_frame, bg=t["bg2"], height=26)
        self.log_hdr.pack(fill="x")
        self.log_hdr.pack_propagate(False)

        for txt, w in [("TIME", 80), ("PROCESS", 160), ("STATUS", 90)]:
            tk.Label(
                self.log_hdr, text=txt,
                font=FONT_XS, bg=t["bg2"], fg=t["fg_mid"],
                width=w // 7, anchor="w",
            ).pack(side="left", padx=(10, 0))

        # Scrollable log body
        self.log_canvas = tk.Canvas(
            self.log_frame, bg=t["bg"],
            highlightthickness=0,
        )
        self.log_sb = tk.Scrollbar(
            self.log_frame, orient="vertical",
            command=self.log_canvas.yview,
        )
        self.log_canvas.configure(yscrollcommand=self.log_sb.set)
        self.log_sb.pack(side="right", fill="y")
        self.log_canvas.pack(side="left", fill="both", expand=True)

        self.log_inner = tk.Frame(self.log_canvas, bg=t["bg"])
        self._log_win  = self.log_canvas.create_window(
            (0, 0), window=self.log_inner, anchor="nw"
        )
        # Keep scroll region and inner width in sync
        self.log_inner.bind("<Configure>", lambda e: self.log_canvas.configure(
            scrollregion=self.log_canvas.bbox("all")
        ))
        self.log_canvas.bind("<Configure>", lambda e: self.log_canvas.itemconfig(
            self._log_win, width=e.width
        ))

        # Empty state placeholder
        self.log_empty = tk.Label(
            self.log_inner, text="no kills logged yet",
            font=FONT_XS, bg=t["bg"], fg=t["fg_dim"],
        )
        self.log_empty.pack(pady=40)

        # Clear button at very bottom
        self.clear_btn = tk.Label(
            self.log_frame, text="CLEAR LOG",
            font=FONT_XS,
            bg=t["tab_bg"], fg=t["fg_mid"],
            cursor="hand2", pady=8,
        )
        self.clear_btn.pack(fill="x", side="bottom")
        self.clear_btn.bind("<Button-1>", lambda e: self._clear_log())
        self.clear_btn.bind("<Enter>",    lambda e: self.clear_btn.config(bg=THEMES[self.theme]["btn_hover"]))
        self.clear_btn.bind("<Leave>",    lambda e: self.clear_btn.config(bg=THEMES[self.theme]["tab_bg"]))

    # ─── Drawing ──────────────────────────────────────────────────────────────

    def _draw_circle(self, pulse_alpha: float = 1.0):
        """
        Render the main circle button.
        pulse_alpha: 0.0–1.0 blends outline between fg and bg for the pulse effect.
        """
        self.canvas.delete("all")
        t  = THEMES[self.theme]
        cx = cy = CANVAS_SZ / 2
        r  = CIRCLE_D / 2
        col = self._blend(t["outline"], t["bg"], pulse_alpha)

        # Subtle hover glow ring
        if self._hover:
            glow = self._blend(t["outline"], t["bg"], 0.10)
            self.canvas.create_oval(
                cx - r - 10, cy - r - 10,
                cx + r + 10, cy + r + 10,
                outline=glow, width=1, fill="",
            )

        # Fine tick marks at 12 clock positions (very subtle depth detail)
        tick_col = self._blend(t["outline"], t["bg"], 0.12)
        for i in range(12):
            ang = math.radians(i * 30)
            r_in  = r - 5
            r_out = r - 1
            self.canvas.create_line(
                cx + r_in  * math.sin(ang), cy - r_in  * math.cos(ang),
                cx + r_out * math.sin(ang), cy - r_out * math.cos(ang),
                fill=tick_col, width=1,
            )

        # Main circle — thin 1.5px outline, no fill
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=col, width=1.5, fill="",
        )

        # Center text: ARMED / SAFE
        self.canvas.create_text(
            cx, cy,
            text="ARMED" if self.armed else "SAFE",
            font=("Consolas", 12, "bold"),
            fill=col,
        )

    def _blend(self, hex_fg: str, hex_bg: str, alpha: float) -> str:
        """Linear blend of two hex colors. alpha=1 → hex_fg, alpha=0 → hex_bg."""
        def parse(h):
            h = h.lstrip("#")
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        fg, bg = parse(hex_fg), parse(hex_bg)
        mixed  = tuple(int(fg[i] * alpha + bg[i] * (1 - alpha)) for i in range(3))
        return "#{:02x}{:02x}{:02x}".format(*mixed)

    def _set_hover(self, state: bool):
        self._hover = state
        if not self._pulse_job:   # don't interrupt pulse
            self._draw_circle()

    # ─── Pulse animation ──────────────────────────────────────────────────────

    def _start_pulse(self):
        self._stop_pulse()
        self._pulse_step()

    def _pulse_step(self):
        """One animation frame — sinusoidal brightness wave."""
        self._pulse_angle += 0.045
        alpha = 0.30 + 0.70 * (0.5 + 0.5 * math.sin(self._pulse_angle))
        self._draw_circle(alpha)
        self._pulse_job = self.root.after(PULSE_MS, self._pulse_step)

    def _stop_pulse(self):
        if self._pulse_job:
            self.root.after_cancel(self._pulse_job)
            self._pulse_job = None

    # ─── Live clock ───────────────────────────────────────────────────────────

    def _start_clock(self):
        self._tick_clock()

    def _tick_clock(self):
        now = datetime.now()
        self.clock_lbl.config(text=now.strftime("%H:%M:%S"))
        self.date_lbl.config(text=now.strftime("%A, %d %B %Y").upper())
        self._clock_job = self.root.after(CLOCK_MS, self._tick_clock)

    # ─── Tab management ───────────────────────────────────────────────────────

    def _switch_tab(self, tab: str):
        if tab == self.active_tab:
            return
        self.active_tab = tab
        self._update_tabs()
        if tab == "home":
            self._show_home()
        else:
            self._show_log()

    def _show_home(self):
        self.log_frame.pack_forget()
        self.home_frame.pack(fill="both", expand=True)
        if self.armed:
            self._start_pulse()
        else:
            self._stop_pulse()
            self._draw_circle()

    def _show_log(self):
        self._stop_pulse()
        self.home_frame.pack_forget()
        self.log_frame.pack(fill="both", expand=True)

    def _update_tabs(self):
        """Refresh tab indicator lines and label colors."""
        t = THEMES[self.theme]
        for frm, lbl, ind, name in [
            (self.tab_home_frm, self.tab_home_lbl, self.tab_home_ind, "home"),
            (self.tab_log_frm,  self.tab_log_lbl,  self.tab_log_ind,  "log"),
        ]:
            active = (name == self.active_tab)
            lbl.config(fg=t["fg"] if active else t["fg_mid"])
            ind.config(bg=t["tab_ln"] if active else t["tab_bg"])

    # ─── Circle interaction ───────────────────────────────────────────────────

    def _on_circle_click(self, event=None):
        """Toggle ARMED / SAFE state."""
        self.armed = not self.armed
        self.state_lbl.config(text="ARMED" if self.armed else "SAFE")
        self.hint_lbl.config(text="F8 active" if self.armed else "F8 inactive")
        if self.armed:
            self._start_pulse()
        else:
            self._stop_pulse()
            self._draw_circle()
        self._save_state()

    # ─── F8 hotkey ────────────────────────────────────────────────────────────

    def _start_hotkey(self):
        """Register F8 in a daemon thread so it doesn't block the UI."""
        if not HAS_KEYBOARD:
            return
        def _listen():
            keyboard.add_hotkey("f8", self._on_f8)
            keyboard.wait()
        threading.Thread(target=_listen, daemon=True, name="veil-hotkey").start()

    def _on_f8(self):
        """F8 handler — called from hotkey thread."""
        if not self.armed:
            return   # SAFE mode: do nothing

        proc, pid = get_foreground_process()

        # Block kill of protected processes or Veil itself
        if proc in PROTECTED or pid == os.getpid():
            self._add_log(proc, "SKIPPED")
            return

        if pid == -1:
            self._add_log("unknown", "ERROR")
            return

        success = kill_pid(pid)
        self._add_log(proc, "KILLED" if success else "ERROR")

    # ─── Kill log ─────────────────────────────────────────────────────────────

    def _add_log(self, process: str, status: str):
        """Thread-safe: schedule log update on main thread."""
        entry = {
            "time":    datetime.now().strftime("%H:%M:%S"),
            "process": process,
            "status":  status,
        }
        self.log_entries.append(entry)
        self.root.after(0, lambda: self._render_row(entry))
        self.root.after(0, self._update_stats)

    def _render_row(self, entry: dict):
        """Append one row to the log table."""
        t   = THEMES[self.theme]
        idx = len(self.log_entries) - 1
        bg  = t["log_alt"] if idx % 2 == 0 else t["bg"]
        col = LOG_COLORS.get(entry["status"], t["fg_mid"])

        # Remove empty-state label on first entry
        if idx == 0:
            self.log_empty.pack_forget()

        row = tk.Frame(self.log_inner, bg=bg)
        row.pack(fill="x")

        tk.Label(row, text=entry["time"],
                 font=FONT_XS, bg=bg, fg=t["fg_mid"],
                 width=10, anchor="w").pack(side="left", padx=(10, 0), pady=5)

        tk.Label(row, text=entry["process"],
                 font=FONT_XS, bg=bg, fg=t["fg"],
                 width=20, anchor="w").pack(side="left")

        tk.Label(row, text=entry["status"],
                 font=FONT_XS, bg=bg, fg=col,
                 width=10, anchor="w").pack(side="left")

        # Thin separator between rows
        tk.Frame(self.log_inner, bg=t["sep"], height=1).pack(fill="x")

        # Auto-scroll to newest entry
        self.log_canvas.update_idletasks()
        self.log_canvas.yview_moveto(1.0)

    def _update_stats(self):
        """Refresh kills / skipped counters on home tab."""
        kills = sum(1 for e in self.log_entries if e["status"] == "KILLED")
        skips = sum(1 for e in self.log_entries if e["status"] == "SKIPPED")
        self.kills_lbl.config(text=f"KILLS  {kills}")
        self.skips_lbl.config(text=f"SKIPPED  {skips}")

    def _clear_log(self):
        """Wipe all log entries from memory and UI."""
        self.log_entries.clear()
        for w in self.log_inner.winfo_children():
            w.destroy()
        t = THEMES[self.theme]
        self.log_empty = tk.Label(
            self.log_inner, text="no kills logged yet",
            font=FONT_XS, bg=t["bg"], fg=t["fg_dim"],
        )
        self.log_empty.pack(pady=40)
        self._update_stats()

    # ─── Theme ────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self._apply_theme(animate=True)
        self._save_state()

    def _apply_theme(self, animate: bool = False):
        """Re-color every widget to match the current theme."""
        t = THEMES[self.theme]

        def _do():
            # All frames and canvases
            for w in [
                self.root, self.root_frame, self.header, self.content,
                self.home_frame, self.stat_bar, self.canvas,
                self.tab_bar, self.tab_home_frm, self.tab_log_frm,
                self.tab_home_lbl, self.tab_log_lbl,
                self.log_frame, self.log_inner, self.log_canvas,
            ]:
                try: w.config(bg=t["bg"])
                except Exception: pass

            try: self.log_hdr.config(bg=t["bg2"])
            except Exception: pass

            for w in [self.sep1, self.sep2, self.tab_div]:
                try: w.config(bg=t["sep"])
                except Exception: pass

            # Labels
            self.clock_lbl.config(bg=t["bg"],     fg=t["fg"])
            self.title_lbl.config(bg=t["bg"],     fg=t["fg_dim"])
            self.date_lbl.config( bg=t["bg"],     fg=t["fg_dim"])
            self.theme_btn.config(bg=t["bg"],     fg=t["fg"],
                text="☀" if self.theme == "dark" else "☽")
            self.state_lbl.config(bg=t["bg"],     fg=t["fg"])
            self.hint_lbl.config( bg=t["bg"],     fg=t["fg_dim"])
            self.kills_lbl.config(bg=t["bg"],     fg=t["fg_dim"])
            self.skips_lbl.config(bg=t["bg"],     fg=t["fg_dim"])
            self.clear_btn.config(bg=t["tab_bg"], fg=t["fg_mid"])

            self._update_tabs()

            if self.armed:
                self._start_pulse()
            else:
                self._draw_circle()

            self._rebuild_log()

        # 3-step rapid apply gives a subtle flash transition (~240ms)
        if animate:
            for i in range(3):
                self.root.after(i * 80, _do)
        else:
            _do()

    def _rebuild_log(self):
        """Redraw all log rows with current theme colors."""
        for w in self.log_inner.winfo_children():
            w.destroy()
        t = THEMES[self.theme]
        if not self.log_entries:
            self.log_empty = tk.Label(
                self.log_inner, text="no kills logged yet",
                font=FONT_XS, bg=t["bg"], fg=t["fg_dim"],
            )
            self.log_empty.pack(pady=40)
        else:
            # Re-render with fresh row index parity
            saved = list(self.log_entries)
            self.log_entries.clear()
            for entry in saved:
                self.log_entries.append(entry)
                self._render_row(entry)

    # ─── System tray ──────────────────────────────────────────────────────────

    def _start_tray(self):
        if not HAS_TRAY:
            return
        icon_img = make_tray_icon(self.theme)
        menu = pystray.Menu(
            pystray.MenuItem("Open Veil", self._show_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._quit_app),
        )
        self._tray_icon = pystray.Icon("Veil", icon_img, "Veil", menu=menu)
        threading.Thread(
            target=self._tray_icon.run,
            daemon=True, name="veil-tray",
        ).start()

    def _show_window(self, *_):
        self.root.after(0, self._do_show_window)

    def _do_show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if self.armed and self.active_tab == "home":
            self._start_pulse()

    def _hide_to_tray(self):
        self._stop_pulse()
        self.root.withdraw()

    def _on_close(self):
        """X button → minimize to tray (not quit)."""
        if HAS_TRAY:
            self._hide_to_tray()
        else:
            self._quit_app()

    def _quit_app(self, *_):
        """Full shutdown — clean up all threads and resources."""
        self._stop_pulse()
        if self._clock_job:
            self.root.after_cancel(self._clock_job)
        self._save_state()
        if self._tray_icon:
            try: self._tray_icon.stop()
            except Exception: pass
        if HAS_KEYBOARD:
            try: keyboard.unhook_all()
            except Exception: pass
        self.root.after(0, self.root.destroy)

    # ─── Persistence ──────────────────────────────────────────────────────────

    def _save_state(self):
        save_config({"theme": self.theme, "armed": self.armed})


# ─── Entry point ───────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.withdraw()     # prevent flash before UI is fully built
    VeilApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
