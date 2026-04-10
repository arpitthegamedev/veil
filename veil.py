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
import time
import threading
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import messagebox

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
    "KILLED":      "#4caf50",
    "SKIPPED":     "#e05555",
    "ERROR":       "#666666",
    "FOCUS-KILL":  "#ff9800",   # orange — auto-killed by Focus Mode
}

# ── Default distraction app list for Focus Mode ───────────────────────────────
DEFAULT_FOCUS_APPS = [
    "instagram.exe", "firefox.exe", "chrome.exe", "vlc.exe",
    "mxplayer.exe", "spotify.exe", "steam.exe", "epicgameslauncher.exe",
    "roblox.exe", "discord.exe", "whatsapp.exe", "telegram.exe",
    "snapchat.exe", "tiktok.exe", "facebook.exe", "twitter.exe",
    "reddit.exe", "9gag.exe", "cs.exe", "hl.exe", "gta_sa.exe",
    "minecraft.exe", "terraria.exe",
]

# Sites that make chrome.exe count as a distraction
CHROME_DISTRACTION_SITES = [
    "youtube", "netflix", "facebook", "instagram",
    "twitter", "reddit", "tiktok", "9gag",
]


# ─── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load persisted config, or return safe defaults."""
    defaults = {
        "theme": "dark", "armed": False,
        "focus_enabled": False,
        "focus_limit_min": 40,
        "focus_apps": list(DEFAULT_FOCUS_APPS),
    }
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

        # ── Focus Mode state ──────────────────────────────────────────────────
        self.focus_enabled   = cfg.get("focus_enabled", False)
        self.focus_limit_min = cfg.get("focus_limit_min", 40)
        self.focus_apps      = list(cfg.get("focus_apps", DEFAULT_FOCUS_APPS))
        self._focus_timers   = {}   # app_name → start timestamp (float)
        self._focus_warned   = set()  # apps that have received the 2-min warning

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
        self._start_focus_monitor()   # ← Focus Mode background scanner

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
        self._build_focus()

        # ── Bottom separator ──────────────────────────────────────────────────
        self.sep2 = tk.Frame(self.root_frame, bg=t["sep"], height=1)
        self.sep2.pack(fill="x")

        # ── Tab bar ───────────────────────────────────────────────────────────
        self.tab_bar = tk.Frame(self.root_frame, bg=t["tab_bg"], height=44)
        self.tab_bar.pack(fill="x")
        self.tab_bar.pack_propagate(False)

        # Two vertical dividers for three equal tabs
        self.tab_div1 = tk.Frame(self.tab_bar, bg=t["sep"], width=1)
        self.tab_div1.place(relx=0.3333, y=0, height=44)
        self.tab_div2 = tk.Frame(self.tab_bar, bg=t["sep"], width=1)
        self.tab_div2.place(relx=0.6667, y=0, height=44)

        # Build each tab (all side="left" + expand=True → equal thirds)
        self.tab_home_frm,  self.tab_home_lbl,  self.tab_home_ind  = self._make_tab("HOME",     "home",  "left")
        self.tab_log_frm,   self.tab_log_lbl,   self.tab_log_ind   = self._make_tab("KILL LOG", "log",   "left")
        self.tab_focus_frm, self.tab_focus_lbl, self.tab_focus_ind = self._make_tab("FOCUS",    "focus", "left")

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
        elif tab == "log":
            self._show_log()
        else:
            self._show_focus()

    def _show_home(self):
        self.log_frame.pack_forget()
        self.focus_frame.pack_forget()
        self.home_frame.pack(fill="both", expand=True)
        if self.armed:
            self._start_pulse()
        else:
            self._stop_pulse()
            self._draw_circle()

    def _show_log(self):
        self._stop_pulse()
        self.home_frame.pack_forget()
        self.focus_frame.pack_forget()
        self.log_frame.pack(fill="both", expand=True)

    def _update_tabs(self):
        """Refresh tab indicator lines and label colors."""
        t = THEMES[self.theme]
        for frm, lbl, ind, name in [
            (self.tab_home_frm,  self.tab_home_lbl,  self.tab_home_ind,  "home"),
            (self.tab_log_frm,   self.tab_log_lbl,   self.tab_log_ind,   "log"),
            (self.tab_focus_frm, self.tab_focus_lbl, self.tab_focus_ind, "focus"),
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
                self.tab_focus_frm, self.tab_focus_lbl,
                self.log_frame, self.log_inner, self.log_canvas,
            ]:
                try: w.config(bg=t["bg"])
                except Exception: pass

            try: self.log_hdr.config(bg=t["bg2"])
            except Exception: pass

            for w in [self.sep1, self.sep2, self.tab_div1, self.tab_div2]:
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
            self._apply_focus_theme()

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
        save_config({
            "theme":            self.theme,
            "armed":            self.armed,
            "focus_enabled":    self.focus_enabled,
            "focus_limit_min":  self.focus_limit_min,
            "focus_apps":       list(self.focus_apps),
        })


    # ─── Focus tab ────────────────────────────────────────────────────────────

    def _build_focus(self):
        """Build the FOCUS tab panel (hidden by default)."""
        t = THEMES[self.theme]
        self.focus_frame = tk.Frame(self.content, bg=t["bg"])

        # ── Header strip (same style as log_hdr) ──────────────────────────────
        self.focus_hdr = tk.Frame(self.focus_frame, bg=t["bg2"], height=26)
        self.focus_hdr.pack(fill="x")
        self.focus_hdr.pack_propagate(False)
        self.focus_hdr_lbl = tk.Label(
            self.focus_hdr, text="FOCUS MODE",
            font=FONT_XS, bg=t["bg2"], fg=t["fg_mid"], anchor="w",
        )
        self.focus_hdr_lbl.pack(side="left", padx=10)

        # ── Controls row ──────────────────────────────────────────────────────
        ctrl = tk.Frame(self.focus_frame, bg=t["bg"])
        ctrl.pack(fill="x", padx=14, pady=(10, 4))
        self.focus_ctrl_frame = ctrl

        # Toggle button (ARMED-style pill)
        self.focus_toggle_btn = tk.Label(
            ctrl,
            text="● ACTIVE" if self.focus_enabled else "○ OFF",
            font=FONT_SM,
            bg=t["bg"], fg="#4caf50" if self.focus_enabled else t["fg_mid"],
            cursor="hand2",
        )
        self.focus_toggle_btn.pack(side="left")
        self.focus_toggle_btn.bind("<Button-1>", lambda e: self._toggle_focus())

        # Time limit control (right side)
        lim_frame = tk.Frame(ctrl, bg=t["bg"])
        lim_frame.pack(side="right")
        self.focus_lim_lbl = tk.Label(
            lim_frame, text="LIMIT",
            font=FONT_XS, bg=t["bg"], fg=t["fg_dim"],
        )
        self.focus_lim_lbl.pack(side="left", padx=(0, 6))

        self.focus_dec_btn = tk.Label(
            lim_frame, text="▼",
            font=FONT_XS, bg=t["bg"], fg=t["fg_mid"], cursor="hand2",
        )
        self.focus_dec_btn.pack(side="left")
        self.focus_dec_btn.bind("<Button-1>", lambda e: self._adj_limit(-5))

        self.focus_min_var = tk.StringVar(value=f"{self.focus_limit_min}m")
        self.focus_min_lbl = tk.Label(
            lim_frame, textvariable=self.focus_min_var,
            font=FONT_SM, bg=t["bg"], fg=t["fg"],
            width=4,
        )
        self.focus_min_lbl.pack(side="left")

        self.focus_inc_btn = tk.Label(
            lim_frame, text="▲",
            font=FONT_XS, bg=t["bg"], fg=t["fg_mid"], cursor="hand2",
        )
        self.focus_inc_btn.pack(side="left")
        self.focus_inc_btn.bind("<Button-1>", lambda e: self._adj_limit(+5))

        # ── Separator ─────────────────────────────────────────────────────────
        self.focus_sep1 = tk.Frame(self.focus_frame, bg=t["sep"], height=1)
        self.focus_sep1.pack(fill="x", pady=(6, 0))

        # ── App list label ────────────────────────────────────────────────────
        self.focus_list_hdr = tk.Label(
            self.focus_frame, text="FLAGGED APPS",
            font=FONT_XS, bg=t["bg"], fg=t["fg_dim"], anchor="w",
        )
        self.focus_list_hdr.pack(fill="x", padx=14, pady=(6, 2))

        # ── Scrollable list of flagged apps ───────────────────────────────────
        list_container = tk.Frame(self.focus_frame, bg=t["bg"])
        list_container.pack(fill="both", expand=True, padx=14)
        self.focus_list_container = list_container

        self.focus_list_canvas = tk.Canvas(
            list_container, bg=t["bg"], highlightthickness=0,
        )
        self.focus_list_sb = tk.Scrollbar(
            list_container, orient="vertical",
            command=self.focus_list_canvas.yview,
        )
        self.focus_list_canvas.configure(yscrollcommand=self.focus_list_sb.set)
        self.focus_list_sb.pack(side="right", fill="y")
        self.focus_list_canvas.pack(side="left", fill="both", expand=True)

        self.focus_list_inner = tk.Frame(self.focus_list_canvas, bg=t["bg"])
        self._focus_list_win = self.focus_list_canvas.create_window(
            (0, 0), window=self.focus_list_inner, anchor="nw"
        )
        self.focus_list_inner.bind("<Configure>", lambda e: self.focus_list_canvas.configure(
            scrollregion=self.focus_list_canvas.bbox("all")
        ))
        self.focus_list_canvas.bind("<Configure>", lambda e: self.focus_list_canvas.itemconfig(
            self._focus_list_win, width=e.width
        ))

        # Render rows
        self._rebuild_focus_list()

        # ── Add-app input strip ───────────────────────────────────────────────
        self.focus_sep2 = tk.Frame(self.focus_frame, bg=t["sep"], height=1)
        self.focus_sep2.pack(fill="x", pady=(4, 0))

        add_row = tk.Frame(self.focus_frame, bg=t["tab_bg"])
        add_row.pack(fill="x", side="bottom")
        self.focus_add_row = add_row

        self.focus_entry_var = tk.StringVar()
        self.focus_entry = tk.Entry(
            add_row,
            textvariable=self.focus_entry_var,
            font=FONT_XS,
            bg=t["bg2"], fg=t["fg"],
            insertbackground=t["fg"],
            relief="flat", bd=0,
        )
        self.focus_entry.pack(side="left", fill="x", expand=True, padx=(10, 6), pady=8)
        self.focus_entry.insert(0, "app.exe")
        self.focus_entry.bind("<FocusIn>",  lambda e: self._entry_focus_in())
        self.focus_entry.bind("<Return>",   lambda e: self._add_focus_app())

        self.focus_add_btn = tk.Label(
            add_row, text="ADD",
            font=FONT_XS, bg=t["tab_bg"], fg=t["fg_mid"],
            cursor="hand2", padx=10, pady=8,
        )
        self.focus_add_btn.pack(side="right")
        self.focus_add_btn.bind("<Button-1>", lambda e: self._add_focus_app())
        self.focus_add_btn.bind("<Enter>",    lambda e: self.focus_add_btn.config(bg=THEMES[self.theme]["btn_hover"]))
        self.focus_add_btn.bind("<Leave>",    lambda e: self.focus_add_btn.config(bg=THEMES[self.theme]["tab_bg"]))

    def _rebuild_focus_list(self):
        """Redraw all app rows in the focus list."""
        t = THEMES[self.theme]
        for w in self.focus_list_inner.winfo_children():
            w.destroy()
        for idx, app in enumerate(self.focus_apps):
            bg = t["log_alt"] if idx % 2 == 0 else t["bg"]
            row = tk.Frame(self.focus_list_inner, bg=bg)
            row.pack(fill="x")
            tk.Label(
                row, text=app,
                font=FONT_XS, bg=bg, fg=t["fg"],
                anchor="w",
            ).pack(side="left", padx=10, pady=4)
            # Delete button
            del_btn = tk.Label(
                row, text="✕",
                font=FONT_XS, bg=bg, fg=t["fg_dim"],
                cursor="hand2",
            )
            del_btn.pack(side="right", padx=8)
            del_btn.bind("<Button-1>", lambda e, a=app: self._remove_focus_app(a))
            del_btn.bind("<Enter>",    lambda e, b=del_btn: b.config(fg="#e05555"))
            del_btn.bind("<Leave>",    lambda e, b=del_btn: b.config(fg=THEMES[self.theme]["fg_dim"]))
            # Row separator
            tk.Frame(self.focus_list_inner, bg=t["sep"], height=1).pack(fill="x")

    def _show_focus(self):
        self._stop_pulse()
        self.home_frame.pack_forget()
        self.log_frame.pack_forget()
        self.focus_frame.pack(fill="both", expand=True)

    def _toggle_focus(self):
        self.focus_enabled = not self.focus_enabled
        t = THEMES[self.theme]
        if self.focus_enabled:
            self.focus_toggle_btn.config(text="● ACTIVE", fg="#4caf50")
            self._focus_timers.clear()
            self._focus_warned.clear()
        else:
            self.focus_toggle_btn.config(text="○ OFF", fg=t["fg_mid"])
            self._focus_timers.clear()
            self._focus_warned.clear()
        self._save_state()

    def _adj_limit(self, delta: int):
        self.focus_limit_min = max(5, min(240, self.focus_limit_min + delta))
        self.focus_min_var.set(f"{self.focus_limit_min}m")
        # Reset timers so new limit applies cleanly
        self._focus_timers.clear()
        self._focus_warned.clear()
        self._save_state()

    def _entry_focus_in(self):
        if self.focus_entry_var.get() == "app.exe":
            self.focus_entry.delete(0, "end")

    def _add_focus_app(self):
        name = self.focus_entry_var.get().strip().lower()
        if not name or name == "app.exe":
            return
        if not name.endswith(".exe"):
            name += ".exe"
        if name not in self.focus_apps:
            self.focus_apps.append(name)
            self._rebuild_focus_list()
            self._save_state()
        self.focus_entry.delete(0, "end")

    def _remove_focus_app(self, app: str):
        if app in self.focus_apps:
            self.focus_apps.remove(app)
            self._focus_timers.pop(app, None)
            self._focus_warned.discard(app)
            self._rebuild_focus_list()
            self._save_state()

    def _apply_focus_theme(self):
        """Re-color all Focus tab widgets to match current theme."""
        t = THEMES[self.theme]
        for w in [
            self.focus_frame, self.focus_ctrl_frame,
            self.focus_list_container, self.focus_list_canvas,
            self.focus_list_inner, self.focus_add_row,
        ]:
            try: w.config(bg=t["bg"])
            except Exception: pass

        try: self.focus_hdr.config(bg=t["bg2"])
        except Exception: pass
        try: self.focus_hdr_lbl.config(bg=t["bg2"], fg=t["fg_mid"])
        except Exception: pass
        try: self.focus_list_hdr.config(bg=t["bg"], fg=t["fg_dim"])
        except Exception: pass
        try: self.focus_lim_lbl.config(bg=t["bg"], fg=t["fg_dim"])
        except Exception: pass
        try: self.focus_min_lbl.config(bg=t["bg"], fg=t["fg"])
        except Exception: pass
        try: self.focus_dec_btn.config(bg=t["bg"], fg=t["fg_mid"])
        except Exception: pass
        try: self.focus_inc_btn.config(bg=t["bg"], fg=t["fg_mid"])
        except Exception: pass
        try:
            if self.focus_enabled:
                self.focus_toggle_btn.config(bg=t["bg"], fg="#4caf50", text="● ACTIVE")
            else:
                self.focus_toggle_btn.config(bg=t["bg"], fg=t["fg_mid"], text="○ OFF")
        except Exception: pass
        try: self.focus_entry.config(bg=t["bg2"], fg=t["fg"], insertbackground=t["fg"])
        except Exception: pass
        try: self.focus_add_btn.config(bg=t["tab_bg"], fg=t["fg_mid"])
        except Exception: pass
        try: self.focus_add_row.config(bg=t["tab_bg"])
        except Exception: pass
        for w in [self.focus_sep1, self.focus_sep2]:
            try: w.config(bg=t["sep"])
            except Exception: pass
        self._rebuild_focus_list()

    # ─── Focus Mode background scanner ────────────────────────────────────────

    def _start_focus_monitor(self):
        """Launch the Focus Mode background thread (daemon, runs every 10s)."""
        def _monitor():
            while True:
                time.sleep(10)
                if not self.focus_enabled or not HAS_WIN32:
                    # Reset all timers while disabled
                    self._focus_timers.clear()
                    self._focus_warned.clear()
                    continue
                try:
                    # Build snapshot of running exe names → Process
                    running = {}
                    for p in psutil.process_iter(["name", "pid"]):
                        try:
                            running[p.info["name"].lower()] = p
                        except Exception:
                            pass

                    now = time.time()
                    limit_secs = self.focus_limit_min * 60
                    warn_secs  = max(0, (self.focus_limit_min - 2) * 60)

                    # Expire timers for apps no longer running
                    for app in list(self._focus_timers.keys()):
                        if app not in running:
                            self._focus_timers.pop(app, None)
                            self._focus_warned.discard(app)

                    for app in list(self.focus_apps):
                        app_lower = app.lower()
                        if app_lower not in running:
                            continue

                        # chrome.exe special case: only count if distraction tab open
                        if app_lower == "chrome.exe":
                            if not self._chrome_has_distraction():
                                self._focus_timers.pop(app_lower, None)
                                self._focus_warned.discard(app_lower)
                                continue

                        # Start timer on first detection
                        if app_lower not in self._focus_timers:
                            self._focus_timers[app_lower] = now
                            continue

                        elapsed = now - self._focus_timers[app_lower]

                        if elapsed >= limit_secs:
                            # ── KILL ──────────────────────────────────────
                            proc = running[app_lower]
                            kill_pid(proc.pid)
                            self._add_log(app_lower, "FOCUS-KILL")
                            self._focus_timers.pop(app_lower, None)
                            self._focus_warned.discard(app_lower)

                        elif elapsed >= warn_secs and app_lower not in self._focus_warned:
                            # ── WARN (once, 2 min before kill) ────────────
                            self._focus_warned.add(app_lower)
                            self.root.after(0, lambda a=app_lower: self._focus_warn_popup(a))

                except Exception:
                    pass

        threading.Thread(target=_monitor, daemon=True, name="veil-focus").start()

    def _focus_warn_popup(self, app: str):
        """Show a non-blocking tkinter warning popup from the main thread."""
        mins = self.focus_limit_min
        messagebox.showwarning(
            "Veil — Focus Mode",
            f"⚠  {app}  closing in 2 minutes\n\n"
            f"You have used this app for {mins - 2}+ minutes.\n"
            f"Focus Mode will force-kill it at {mins} minutes.",
            parent=self.root,
        )

    def _chrome_has_distraction(self) -> bool:
        """Return True if any visible window title contains a distraction site."""
        if not HAS_WIN32:
            return False
        found = []
        def _check(hwnd, _):
            try:
                title = win32gui.GetWindowText(hwnd).lower()
                if any(s in title for s in CHROME_DISTRACTION_SITES):
                    found.append(True)
            except Exception:
                pass
        try:
            win32gui.EnumWindows(_check, None)
        except Exception:
            pass
        return bool(found)


# ─── Entry point ───────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.withdraw()     # prevent flash before UI is fully built
    VeilApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
