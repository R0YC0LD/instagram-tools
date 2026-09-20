"""
igdm_intro.py
Opening screen: film-style credits scrolling from bottom to top over a night-sky background, while a little
Pacman chomps along the bottom edge. Click or press any key to skip.

Pure tkinter (no heavy imports) - it is shown immediately while the real app loads in the background.
"""

import math
import random
import time
import tkinter as tk

from igdm_icon import logo_image
from igdm_meta import APP_TITLE, VERSION, AUTHOR, INSTAGRAM_HANDLE, REPO_URL

TOP, BOTTOM = (5, 8, 20), (24, 30, 72)
PAC = "#facc15"
RED = "#e30a17"
WHITE = "#f8fafc"
MUTED = "#94a3b8"
DIM = "#64748b"
PINK = "#f472b6"
FONT = "Segoe UI"


def spaced(text):
    """Letter-spaced caps for small labels."""
    return " ".join(text.upper()).replace("   ", "   ")


def credit_items():
    """(kind, text, font, colour, gap_after_px) - the whole roll, top to bottom."""
    return [
        ("image", None, None, None, 26),
        ("text", APP_TITLE, (FONT, 30, "bold"), WHITE, 6),
        ("text", f"v{VERSION}  ·  Instagram için Pacman'li temizlik aracı", (FONT, 12), MUTED, 92),

        ("text", "☪", ("Segoe UI Symbol", 34), RED, 6),
        ("text", spaced("Made in Türkiye"), (FONT, 20, "bold"), WHITE, 92),

        ("text", spaced("Made by"), (FONT, 11), DIM, 10),
        ("text", AUTHOR, (FONT, 30, "bold"), PAC, 92),

        ("text", spaced("Instagram"), (FONT, 11), DIM, 10),
        ("text", f"@{INSTAGRAM_HANDLE}", (FONT, 26, "bold"), PINK, 92),

        ("text", "Ücretsiz ve açık kaynak  ·  MIT Lisansı", (FONT, 12), MUTED, 8),
        ("text", REPO_URL, (FONT, 12), "#a5b4fc", 92),

        ("text", "●   ●   ●", (FONT, 14), PAC, 14),
        ("text", "Hesabını hafiflet. Pacman yesin.", (FONT, 13, "italic"), MUTED, 60),
    ]


def _mix(a, b, t):
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Intro:
    def __init__(self, root, on_done=None, speed=150.0):
        """speed: scroll speed in pixels per second."""
        self.root = root
        self.on_done = on_done
        self.speed = speed
        self.done = False
        self._after = None
        self._built = False
        self._last = time.perf_counter()
        self.logo = logo_image(large=True)

        self.frame = tk.Frame(root, bg=_mix(TOP, BOTTOM, 0))
        self.frame.place(x=0, y=0, relwidth=1, relheight=1)
        self.cv = tk.Canvas(self.frame, bg=_mix(TOP, BOTTOM, 0), highlightthickness=0, cursor="hand2")
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Configure>", self._on_configure)
        self.cv.bind("<Button-1>", lambda e: self.skip())
        self._key = root.bind("<Key>", lambda e: self.skip(), add="+")
        self._pac_x = -40.0
        self._t0 = time.perf_counter()
        self._stars = []
        self._dots = {}
        self._pac = None
        self._after = root.after(16, self._tick)

    # ---- layout ------------------------------------------------------------------------------
    def _on_configure(self, event):
        w, h = event.width, event.height
        if w < 50 or h < 50:
            return
        self._draw_background(w, h)
        if not self._built:
            self._built = True
            self._build_credits(w, h)
        self._draw_pacman_strip(w, h)
        self._draw_bottom_bar(w, h)
        for layer in ("credits", "bar", "strip", "ui"):      # stacking order, bottom -> top
            self.cv.tag_raise(layer)

    def _draw_bottom_bar(self, w, h):
        """Opaque band under the credits: text slides *behind* it, so the Pacman strip stays clean."""
        self.cv.delete("bar")
        self.cv.create_rectangle(0, h - 100, w, h, fill=_mix(TOP, BOTTOM, 1.0), outline="", tags="bar")

    def _draw_background(self, w, h):
        self.cv.delete("bg")
        bands = 56
        for i in range(bands):
            y0, y1 = h * i // bands, h * (i + 1) // bands + 1
            self.cv.create_rectangle(0, y0, w, y1, fill=_mix(TOP, BOTTOM, i / (bands - 1)), outline="", tags="bg")
        self._stars = []
        rnd = random.Random(7)
        for _ in range(90):
            x, y, r = rnd.randint(0, w), rnd.randint(0, h), rnd.choice((1, 1, 1, 2))
            self._stars.append(self.cv.create_oval(x, y, x + r, y + r, fill="#475569", outline="", tags="bg"))
        self.cv.tag_lower("bg")

    def _build_credits(self, w, h):
        self.cv.delete("credits")
        y = h + 30
        for kind, text, font, fill, gap in credit_items():
            if kind == "image":
                item = self.cv.create_image(w // 2, y, image=self.logo, anchor="n", tags="credits")
            else:
                item = self.cv.create_text(w // 2, y, text=text, font=font, fill=fill, anchor="n", tags="credits",
                                           justify="center", width=w - 80)
            x0, y0, x1, y1 = self.cv.bbox(item)
            y = y1 + gap
        self.cv.create_text(24, h - 22, text="Atlamak için tıkla ya da bir tuşa bas", anchor="sw", fill=DIM,
                            font=(FONT, 9), tags="ui")
        self.cv.create_text(w - 24, h - 22, text="Geç  ›", anchor="se", fill=MUTED,
                            font=(FONT, 11, "bold"), tags="ui")

    def _draw_pacman_strip(self, w, h):
        self.cv.delete("strip")
        y = h - 62
        self._strip_y = y
        self._dots = {}
        for x in range(60, w - 30, 30):
            self._dots[x] = self.cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#fde68a", outline="", tags="strip")
        self._pac = self.cv.create_arc(0, 0, 0, 0, start=30, extent=300, fill=PAC, outline="", tags="strip")

    # ---- animation ---------------------------------------------------------------------------
    def _tick(self):
        if self.done:
            return
        now = time.perf_counter()
        dt = min(now - self._last, 0.05)
        self._last = now
        try:
            self.cv.move("credits", 0, -self.speed * dt)
            self._animate_pacman(now, dt)
            if self._stars and random.random() < 0.35:
                s = random.choice(self._stars)
                self.cv.itemconfigure(s, fill=random.choice(("#475569", "#94a3b8", "#e2e8f0", "#64748b")))
            box = self.cv.bbox("credits")
            if self._built and box and box[3] < -10:
                self.finish()
                return
        except tk.TclError:
            return
        self._after = self.root.after(16, self._tick)

    def _animate_pacman(self, now, dt):
        if self._pac is None:
            return
        w = self.cv.winfo_width()
        self._pac_x += 150 * dt
        if self._pac_x > w + 30:
            self._draw_pacman_strip(w, self.cv.winfo_height())
            self._pac_x = -30.0
        x, y = self._pac_x, self._strip_y
        mouth = 4 + 34 * abs(math.sin((now - self._t0) * 9))
        self.cv.coords(self._pac, x - 15, y - 15, x + 15, y + 15)
        self.cv.itemconfigure(self._pac, start=mouth, extent=360 - 2 * mouth)
        for dx in [d for d in self._dots if d <= x + 6]:
            self.cv.delete(self._dots.pop(dx))

    # ---- end ---------------------------------------------------------------------------------
    def lift(self):
        try:
            self.frame.lift()
        except tk.TclError:
            pass

    def skip(self):
        self.finish()

    def finish(self):
        if self.done:
            return
        self.done = True
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
        try:
            self.root.unbind("<Key>", self._key)
        except tk.TclError:
            pass
        try:
            self.frame.destroy()
        except tk.TclError:
            pass
        if self.on_done:
            self.on_done()
