"""
igdm_ui.py
The look & feel of the app: theme, flat buttons, modal dialogs, sidebar navigation, empty-state hints.
Pure Tk/ttk (no extra dependencies).
"""

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

from igdm_common import (ACCENT, ACCENT_DARK, DANGER, DANGER_DARK, SUCCESS, WARN, PAC, BG, CARD, BORDER, TEXT, MUTED,
                         SIDEBAR, SIDEBAR_HOVER, SIDEBAR_TEXT, FONT, FONT_BOLD)
from igdm_icon import icon_path, set_window_icon, logo_image  # noqa: F401  (re-exported for the app)
from igdm_i18n import tr


# ------------------------------------------------------------------------------------------ theme
def apply_style(root):
    st = ttk.Style(root)
    st.theme_use("clam")
    root.configure(bg=BG)
    # default font for the classic tk widgets only (a "*Font" option would also override ttk style fonts)
    for cls in ("Label", "Button", "Text", "Entry", "Listbox", "Menu"):
        root.option_add(f"*{cls}.Font", (FONT, 10))
    st.configure(".", font=(FONT, 10), background=BG, foreground=TEXT, bordercolor=BORDER, focuscolor=BG)

    st.configure("TFrame", background=BG)
    st.configure("Card.TFrame", background=CARD)
    st.configure("Page.TFrame", background=CARD, relief="solid", borderwidth=1, bordercolor=BORDER,
                 lightcolor=BORDER, darkcolor=BORDER)
    st.configure("TLabel", background=BG, foreground=TEXT)
    st.configure("Card.TLabel", background=CARD, foreground=TEXT)
    st.configure("Title.TLabel", background=BG, font=(FONT, 16, "bold"))
    st.configure("H.TLabel", background=CARD, foreground=TEXT, font=(FONT, 15, "bold"))
    st.configure("Sub.TLabel", background=CARD, foreground=MUTED)
    st.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT, 9))

    st.configure("TCheckbutton", background=CARD, foreground=TEXT, focuscolor=CARD)
    st.map("TCheckbutton", background=[("active", CARD)], indicatorcolor=[("selected", ACCENT), ("!selected", "white")])
    st.configure("Bg.TCheckbutton", background=BG, focuscolor=BG)
    st.map("Bg.TCheckbutton", background=[("active", BG)], indicatorcolor=[("selected", ACCENT), ("!selected", "white")])

    for name in ("TEntry", "TSpinbox", "TCombobox"):
        st.configure(name, fieldbackground="white", background="white", foreground=TEXT, bordercolor="#d1d5db",
                     lightcolor="#d1d5db", darkcolor="#d1d5db", padding=(8, 6), arrowcolor=MUTED, insertcolor=TEXT)
        st.map(name, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)],
               fieldbackground=[("readonly", "white"), ("disabled", "#f3f4f6")])
    st.map("TCombobox", selectbackground=[("readonly", "white")], selectforeground=[("readonly", TEXT)])

    st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=30, borderwidth=0,
                 font=(FONT, 10))
    st.configure("Treeview.Heading", background="#f3f4f6", foreground="#374151", font=(FONT, 10, "bold"), relief="flat",
                 padding=(10, 7), borderwidth=0)
    st.map("Treeview", background=[("selected", "#e0e7ff")], foreground=[("selected", TEXT)])
    st.map("Treeview.Heading", background=[("active", "#e5e7eb")])

    st.configure("Horizontal.TProgressbar", troughcolor="#e5e7eb", background=ACCENT, bordercolor="#e5e7eb",
                 lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
    st.configure("Vertical.TScrollbar", troughcolor="#f3f4f6", background="#cbd5e1", bordercolor="#f3f4f6",
                 arrowcolor="#6b7280", relief="flat", gripcount=0, arrowsize=12)
    st.map("Vertical.TScrollbar", background=[("active", "#94a3b8")])
    st.configure("TSeparator", background=BORDER)

    apply_checkbox_style(root, st)

    # Notebook used as a page container: no tab strip, no border (navigation lives in the sidebar)
    st.layout("Nav.TNotebook.Tab", [])
    st.configure("Nav.TNotebook", background=BG, borderwidth=0, tabmargins=0, padding=0)
    st.layout("Nav.TNotebook", [("Notebook.client", {"sticky": "nswe"})])


# ---------------------------------------------------------------------------------------- buttons
_KINDS = {
    #            bg       hover        fg       disabled bg
    "primary":   (ACCENT, ACCENT_DARK, "white", "#c7d2fe"),
    "danger":    (DANGER, DANGER_DARK, "white", "#fecaca"),
    "secondary": ("#e5e7eb", "#d1d5db", TEXT, "#f3f4f6"),
    "ghost":     (SIDEBAR, SIDEBAR_HOVER, SIDEBAR_TEXT, SIDEBAR),
    "success":   (SUCCESS, "#15803d", "white", "#bbf7d0"),
}


class FlatButton(tk.Button):
    """Flat button with hover effect and a proper disabled look. Drop-in for tk.Button."""

    def __init__(self, master, text, command, kind="primary", **kw):
        self.kind = kind
        bg, _, fg, _ = _KINDS[kind]
        opts = dict(text=text, command=command, bg=bg, fg=fg, activebackground=_KINDS[kind][1],
                    activeforeground=fg, relief="flat", bd=0, padx=16, pady=8, font=(FONT, 10, "bold"),
                    cursor="hand2", takefocus=1, highlightthickness=0)
        opts.update(kw)
        super().__init__(master, **opts)
        self.bind("<Enter>", lambda e: self._paint(hover=True))
        self.bind("<Leave>", lambda e: self._paint(hover=False))

    def _paint(self, hover=False):
        bg, hov, fg, dis = _KINDS[self.kind]
        try:
            disabled = str(super().cget("state")) == "disabled"
        except tk.TclError:
            return
        if disabled:
            tk.Button.configure(self, bg=dis, fg="#9ca3af" if self.kind != "ghost" else "#475569", cursor="arrow")
        else:
            tk.Button.configure(self, bg=hov if hover else bg, fg=fg, cursor="hand2")

    def configure(self, cnf=None, **kw):
        r = super().configure(cnf, **kw)
        if "state" in kw or (isinstance(cnf, dict) and "state" in cnf):
            self._paint()
        return r

    config = configure


# ---------------------------------------------------------------------------------------- dialogs
_GLYPHS = {"info": ("i", ACCENT), "warn": ("!", WARN), "error": ("✕", DANGER), "ask": ("?", ACCENT),
           "danger": ("!", DANGER)}


def _root():
    return tk._default_root


def _dialog(title, message, kind, buttons, entry=False, initial="", parent=None, default=None, width=460):
    """Modal, themed dialog. buttons: [(label, value, style)]. -> value of the pressed button
    (or the entered text when entry=True and a 'primary' button is pressed, None on cancel)."""
    parent = parent or _root()
    dlg = tk.Toplevel(parent)
    dlg.withdraw()
    dlg.title(title)
    dlg.configure(bg=CARD)
    visible = bool(parent.winfo_viewable())
    if visible:                      # a transient of a hidden window would itself stay invisible
        dlg.transient(parent)
    dlg.resizable(False, False)
    set_window_icon(dlg)
    result = {"v": None}

    body = tk.Frame(dlg, bg=CARD)
    body.pack(fill="both", expand=True, padx=26, pady=(24, 8))
    glyph, color = _GLYPHS.get(kind, _GLYPHS["info"])
    cv = tk.Canvas(body, width=46, height=46, bg=CARD, highlightthickness=0)
    cv.create_oval(2, 2, 44, 44, fill=color, outline="")
    cv.create_text(23, 23, text=glyph, fill="white", font=(FONT, 17, "bold"))
    cv.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 16))
    tk.Label(body, text=title, bg=CARD, fg=TEXT, font=(FONT, 13, "bold"), anchor="w", justify="left",
             wraplength=width).grid(row=0, column=1, sticky="w")
    tk.Label(body, text=message, bg=CARD, fg="#374151", font=(FONT, 10), anchor="w", justify="left",
             wraplength=width).grid(row=1, column=1, sticky="w", pady=(6, 0))

    ent = None
    if entry:
        var = tk.StringVar(value=initial)
        ent = ttk.Entry(body, textvariable=var, width=38, font=(FONT, 11))
        ent.grid(row=2, column=1, sticky="w", pady=(14, 0))
    btnbar = tk.Frame(dlg, bg="#f9fafb")
    btnbar.pack(fill="x", pady=(18, 0))
    inner = tk.Frame(btnbar, bg="#f9fafb")
    inner.pack(side="right", padx=20, pady=14)

    def finish(value):
        result["v"] = (var.get() if (entry and value is True) else value)
        dlg.destroy()

    made = []
    for label, value, style in buttons:
        b = FlatButton(inner, label, lambda v=value: finish(v), kind=style)
        b.pack(side="left", padx=(8, 0))
        made.append(b)
    default = default if default is not None else next((i for i, (_, _, s) in enumerate(buttons) if s != "secondary"), 0)
    # keyboard actions are also exposed as plain callables (used by tests, independent of window focus)
    dlg.press_escape = lambda: finish(None if entry else False)
    dlg.press_enter = lambda: made[default].invoke()
    dlg.bind("<Escape>", lambda e: dlg.press_escape())
    dlg.bind("<Return>", lambda e: dlg.press_enter())
    dlg.protocol("WM_DELETE_WINDOW", dlg.press_escape)

    dlg.update_idletasks()
    try:
        if visible:
            x = parent.winfo_rootx() + (parent.winfo_width() - dlg.winfo_reqwidth()) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - dlg.winfo_reqheight()) // 3
        else:
            x = (dlg.winfo_screenwidth() - dlg.winfo_reqwidth()) // 2
            y = (dlg.winfo_screenheight() - dlg.winfo_reqheight()) // 3
    except tk.TclError:
        x = y = 200
    dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    dlg.deiconify()
    dlg.grab_set()
    (ent or made[default]).focus_force()
    if ent is not None:
        ent.select_range(0, "end")
    parent.wait_window(dlg)
    return result["v"]


def showinfo(title, message, parent=None):
    _dialog(title, message, "info", [(tr("Tamam"), True, "primary")], parent=parent)


def showwarning(title, message, parent=None):
    _dialog(title, message, "warn", [(tr("Tamam"), True, "primary")], parent=parent)


def showerror(title, message, parent=None):
    _dialog(title, message, "error", [(tr("Tamam"), True, "primary")], parent=parent)


def askyesno(title, message, parent=None):
    """Destructive prompts: the safe answer ('Hayır') is the default for Enter."""
    return bool(_dialog(title, message, "ask", [(tr("Hayır"), False, "secondary"), (tr("Evet, devam et"), True, "danger")],
                        parent=parent, default=0))


def askstring(title, prompt, parent=None, initialvalue=""):
    """-> entered text, or None when cancelled."""
    return _dialog(title, prompt, "ask", [(tr("Vazgeç"), None, "secondary"), (tr("Tamam"), True, "primary")],
                   entry=True, initial=initialvalue, parent=parent, default=1)


# --------------------------------------------------------------------------------- sidebar / nav
class NavNotebook(ttk.Notebook):
    """ttk.Notebook whose tab strip is hidden; a Sidebar drives it and mirrors tab state."""

    def __init__(self, master, **kw):
        super().__init__(master, style="Nav.TNotebook", **kw)
        self.nav = None

    def tab(self, tab_id, option=None, **kw):
        r = super().tab(tab_id, option, **kw)
        if kw and self.nav is not None:
            self.nav.refresh()
        return r

    def select(self, tab_id=None):
        r = super().select(tab_id)
        if tab_id is not None and self.nav is not None:
            self.nav.refresh()
        return r


class Sidebar(tk.Frame):
    WIDTH = 250

    def __init__(self, master, nb, sections, logo, title, subtitle):
        super().__init__(master, bg=SIDEBAR, width=self.WIDTH)
        self.pack_propagate(False)
        self.nb = nb
        self.rows = {}
        self.logo = logo

        # The footer is packed FIRST so that, in a short window, it is the nav list that gets clipped, never the footer.
        self.footer = tk.Frame(self, bg=SIDEBAR)
        self.footer.pack(side="bottom", fill="x", padx=16, pady=14)

        brand = tk.Frame(self, bg=SIDEBAR)
        brand.pack(fill="x", padx=16, pady=(18, 4))
        tk.Label(brand, image=logo, bg=SIDEBAR).pack(side="left")
        col = tk.Frame(brand, bg=SIDEBAR)
        col.pack(side="left", fill="x", expand=True, padx=(10, 0))
        size = 12                                       # shrink the name until it fits, whatever the language
        room = self.WIDTH - 32 - logo.width() - 14
        while size > 9 and tkfont.Font(family=FONT, size=size, weight="bold").measure(title) > room:
            size -= 1
        tk.Label(col, text=title, fg="white", bg=SIDEBAR, font=(FONT, size, "bold"), anchor="w").pack(fill="x")
        tk.Label(col, text=subtitle, fg="#94a3b8", bg=SIDEBAR, font=(FONT, 9), anchor="w").pack(fill="x")

        for section, items in sections:
            tk.Label(self, text=section, fg="#64748b", bg=SIDEBAR, font=(FONT, 8, "bold"), anchor="w").pack(
                fill="x", padx=22, pady=(12, 3))
            for idx, text, glyph in items:
                self._add_item(idx, text, glyph)

        nb.nav = self
        nb.bind("<<NotebookTabChanged>>", lambda e: self.refresh(), add="+")

    def _add_item(self, idx, text, glyph):
        row = tk.Frame(self, bg=SIDEBAR, height=35, cursor="hand2")
        row.pack(fill="x", padx=(0, 0), pady=1)
        row.pack_propagate(False)
        stripe = tk.Frame(row, bg=SIDEBAR, width=4)
        stripe.pack(side="left", fill="y")
        g = tk.Label(row, text=glyph, bg=SIDEBAR, fg=SIDEBAR_TEXT, font=("Segoe UI Symbol", 12), width=3)
        g.pack(side="left", padx=(12, 0))
        t = tk.Label(row, text=text, bg=SIDEBAR, fg=SIDEBAR_TEXT, font=(FONT, 10), anchor="w")
        t.pack(side="left", fill="x", expand=True)
        widgets = (row, g, t)
        for w in widgets:
            w.bind("<Button-1>", lambda e, i=idx: self.go(i))
            w.bind("<Enter>", lambda e, i=idx: self._hover(i, True))
            w.bind("<Leave>", lambda e, i=idx: self._hover(i, False))
        self.rows[idx] = {"row": row, "stripe": stripe, "glyph": g, "text": t, "hover": False}

    def _state(self, idx):
        try:
            return str(self.nb.tab(idx, "state"))
        except tk.TclError:
            return "disabled"

    def _current(self):
        try:
            return self.nb.index(self.nb.select())
        except tk.TclError:
            return -1

    def go(self, idx):
        if self._state(idx) == "normal":
            self.nb.select(idx)

    def _hover(self, idx, on):
        self.rows[idx]["hover"] = on
        self._paint(idx, self._current())            # only the row under the mouse: cheap, no flicker

    def refresh(self):
        cur = self._current()
        for idx in self.rows:
            self._paint(idx, cur)

    def _paint(self, idx, cur):
        r = self.rows[idx]
        state = self._state(idx)
        active = idx == cur
        if state != "normal":
            bg, fg, stripe = SIDEBAR, "#475569", SIDEBAR
        elif active:
            bg, fg, stripe = SIDEBAR_HOVER, "white", PAC
        elif r["hover"]:
            bg, fg, stripe = SIDEBAR_HOVER, "white", SIDEBAR_HOVER
        else:
            bg, fg, stripe = SIDEBAR, SIDEBAR_TEXT, SIDEBAR
        sig = (bg, fg, stripe, state == "normal", active)
        if r.get("sig") == sig:                      # nothing changed -> no Tk calls at all
            return
        r["sig"] = sig
        r["row"].configure(bg=bg, cursor="hand2" if state == "normal" else "arrow")
        r["stripe"].configure(bg=stripe)
        r["glyph"].configure(bg=bg, fg=PAC if (active and state == "normal") else fg)
        r["text"].configure(bg=bg, fg=fg, font=(FONT, 10, "bold" if active else "normal"))


# --------------------------------------------------------------------------------- empty states
class EmptyHints:
    """Shows a centred hint on top of a Treeview while it has no rows (updated on every insert/delete)."""

    def __init__(self, root):
        self.root = root
        self.items = []

    def add(self, tree, text):
        lbl = tk.Label(tree, text=text, bg=CARD, fg="#9ca3af", font=(FONT, 10), justify="center")
        self.items.append((tree, lbl))
        orig_insert, orig_delete = tree.insert, tree.delete

        def insert(*a, **k):
            r = orig_insert(*a, **k)
            self._sync(tree, lbl)
            return r

        def delete(*a, **k):
            r = orig_delete(*a, **k)
            self._sync(tree, lbl)
            return r

        tree.insert, tree.delete = insert, delete
        self._sync(tree, lbl)
        return lbl

    @staticmethod
    def _sync(tree, lbl):
        try:
            if tree.get_children():
                lbl.place_forget()
            else:
                lbl.place(relx=0.5, rely=0.5, anchor="center")
        except tk.TclError:
            pass


# ------------------------------------------------------------------------------- checkboxes
def _checkbox_image(checked, disabled=False, size=20):
    """Draw a rounded checkbox as a PhotoImage (anti-aliased by supersampling the coverage test)."""
    import math
    img = tk.PhotoImage(width=size, height=size)
    border = "#d1d5db" if disabled else ("#4f46e5" if checked else "#9ca3af")
    fill = ("#c7d2fe" if disabled else ACCENT) if checked else ("#f3f4f6" if disabled else "#ffffff")
    r, m = 4.5, 2.0                                       # corner radius, outer margin

    def inside(x, y, inset):
        lo, hi = m + inset, size - m - inset
        if not (lo <= x <= hi and lo <= y <= hi):
            return False
        cx = min(max(x, lo + r - inset), hi - r + inset)
        cy = min(max(y, lo + r - inset), hi - r + inset)
        return (x - cx) ** 2 + (y - cy) ** 2 <= (r - inset) ** 2 or (lo + r - inset <= x <= hi - r + inset) or (
            lo + r - inset <= y <= hi - r + inset)

    def dist_seg(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    tick = [(5.2, 10.4), (8.6, 13.8), (14.8, 6.6)]
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            hits = {"edge": 0, "body": 0, "tick": 0}
            for sy in (0.25, 0.75):
                for sx in (0.25, 0.75):
                    px, py = x + sx, y + sy
                    if inside(px, py, 0):
                        hits["body" if inside(px, py, 1.4) else "edge"] += 1
                    if checked and (dist_seg(px, py, *tick[0], *tick[1]) <= 1.15 or dist_seg(px, py, *tick[1], *tick[2]) <= 1.15):
                        hits["tick"] += 1
            if hits["tick"] >= 2:
                row.append("#ffffff")
            elif hits["body"] + hits["edge"] == 0:
                row.append(CARD)
            elif hits["edge"] > 0 and hits["body"] < 4:
                row.append(border)
            else:
                row.append(fill)
        rows.append("{" + " ".join(row) + "}")
    img.put(" ".join(rows))
    return img


def apply_checkbox_style(root, st):
    """Replace the clunky default indicator by rounded images (kept referenced on root)."""
    if "modern.indicator" in st.element_names() and getattr(root, "_chk_imgs", None):
        return                                        # window rebuilt (language change): style already in place
    root._chk_imgs = (_checkbox_image(False), _checkbox_image(True), _checkbox_image(False, True),
                      _checkbox_image(True, True))
    off, on, off_d, on_d = root._chk_imgs
    st.element_create("modern.indicator", "image", off, ("disabled", "selected", on_d), ("disabled", off_d),
                      ("selected", on), sticky="w", padding=(0, 0, 6, 0))
    st.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("modern.indicator", {"side": "left", "sticky": ""}),
        ("Checkbutton.focus", {"side": "left", "sticky": "", "children": [("Checkbutton.label", {"sticky": "nswe"})]})]})])
