#!/usr/bin/env python3
"""
igdm_app.py
PACMANGRAM main window (English / Turkish UI).

Reuses the hardened core in igdm_core.py: importing it installs the network
allowlist (Instagram/Facebook hosts only) and gives us the DPAPI-encrypted
session store.
"""

import os
import sys
import json
import time
import queue
import random
import ctypes
import threading
import traceback
from datetime import datetime
import tkinter as tk
from tkinter import ttk

import igdm_core as core  # installs the network guard on import
from igdm_core import (Client, BlockedDestination, SESSION_FILE, APP_DIR,
                      load_session, save_session, wipe_session)
from instagrapi.exceptions import (TwoFactorRequired, BadPassword, ChallengeRequired, PleaseWaitFewMinutes,
                                   RateLimitError, FeedbackRequired, ClientThrottledError, LoginRequired)

import igdm_ui as ui
import igdm_perf as perf
from igdm_common import (VERSION, ACCENT, ACCENT_DARK, DANGER, BG, CARD, TEXT, MUTED, PAC, SIDEBAR,
                         SIDEBAR_HOVER, FONT, FONT_BOLD, SETTINGS_FILE, PROTECTED_FILE, KEEP_FILE,
                         LOG_FILE, PROFILES, DEFAULT_PROFILE, SOFT_PAUSE, MAX_SOFT_HITS, LONG_REST, MAX_LONG_RESTS,
                         StopRequested, Pacer, fmt_duration, load_json, save_json, limit_kind, is_limit_error,
                         is_network_error, NET_BACKOFF, friendly, norm_word, profile_label, profile_id)
from igdm_bulk import StoryTab, BlockedTab, LikesTab, SavedTab
from igdm_extra import BackupTab, AccountTab


from igdm_items import ITEM_LABELS, item_id, item_text, item_label, item_time  # noqa: F401
from igdm_i18n import tr, T, app_title, LANGS, CODES, NAMES, get_language, set_language





class App:
    def __init__(self, root, carry=None):
        self.root = root
        self.q = queue.Queue()                           # UI callbacks posted by worker threads
        self._log_q = queue.Queue()                      # log lines -> file, written off the UI thread
        self._log_thread = None
        self._poll_id = None
        self._setup(carry)

    def _setup(self, carry=None):
        """Build (or, after a language change, rebuild) the whole window. `carry` keeps the login."""
        root = self.root
        self.client = None
        self.my_username = None
        self.my_user_id = None
        self.thread_id = None
        self.thread_name = ""
        self.inbox_cursor = None
        self.inbox_has_more = False
        self.threads = []
        self.found = {}
        self.more_older = False
        self.auto_threads = []   # every inbox thread, newest first
        self.auto_todo = []      # threads the current plan would delete
        self.auto_reason = {}    # thread_id -> "auto" | "manual" | "pin" for kept threads
        self.protected = set()   # chats the user double-clicked green ("never delete")
        self.pacer = Pacer(DEFAULT_PROFILE)
        self.soft_hits = 0
        self.long_rests = 0
        self.auto_resume = True
        self.bulk_tabs = []      # StoryTab / BlockedTab / LikesTab
        self._status_lbl = None
        self.busy = False
        self.stop_event = threading.Event()
        self.frame_ms = perf.frame_ms()                  # one display frame: 16 ms @60 Hz, 6 ms @144 Hz
        self.poll_ms = max(4, self.frame_ms)             # UI-queue polling follows the display

        root.title(f"{app_title()} v{VERSION}")
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = min(1340, sw - 40), min(860, sh - 90)
        if not getattr(root, "_igdm_sized", False):      # the launcher may already have sized the window
            root.geometry(f"{w}x{h}+{max((sw - w) // 2, 0)}+{max((sh - h) // 3, 0)}")
        root.minsize(min(1180, w), min(700, h))
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.report_callback_exception = self._tk_exception

        saved = load_json(SETTINGS_FILE, {})
        if carry is None and saved.get("language") in CODES:
            set_language(saved["language"])                # otherwise keep the language chosen by the launcher / tests
        root.title(f"{app_title()} v{VERSION}")
        prof = saved.get("profile")
        self.var_profile = tk.StringVar(value=prof if prof in PROFILES else DEFAULT_PROFILE)
        self.var_profile_disp = tk.StringVar(value=profile_label(self.var_profile.get()))
        self.var_lang_disp = tk.StringVar(value=NAMES[get_language()])
        self.var_keep = tk.IntVar(value=int(saved.get("keep", 20)) if str(saved.get("keep", 20)).isdigit() else 20)
        self.var_keep_pins = tk.BooleanVar(value=bool(saved.get("keep_pins", True)))
        self.var_unsend_first = tk.BooleanVar(value=bool(saved.get("unsend_first", False)))
        self.var_auto_filter = tk.StringVar()
        self.var_autoresume = tk.BooleanVar(value=bool(saved.get("auto_resume", True)))

        self._style()
        self._build()
        self._poll_id = self.root.after(self.poll_ms, self._poll)
        self.log(tr("Program açıldı. Ağ kilidi aktif: yalnızca Instagram/Facebook sunucularına bağlanılır."))
        if carry and carry.get("client") is not None:
            self._restore_login(carry)
        else:
            self.try_saved_session()

    # ------------------------------------------------------------- language
    def change_language(self, code):
        """Switch the display language on the fly: the window is rebuilt, the login (and page) are kept."""
        if code not in CODES or code == get_language():
            return False
        if self.busy:
            ui.showinfo(app_title(), tr("Bir işlem sürerken dil değiştirilemez. Önce işlemi durdur."))
            self.var_lang_disp.set(NAMES[get_language()])
            return False
        try:
            page = self.nb.index(self.nb.select())
        except tk.TclError:
            page = 0
        carry = {"client": self.client, "username": self.my_username, "uid": self.my_user_id, "page": page}
        self.flush_log(1.0)
        set_language(code)
        self.save_settings()                              # (writes "language": code)
        if self._poll_id is not None:
            try:
                self.root.after_cancel(self._poll_id)
            except tk.TclError:
                pass
        for w in list(self.root.winfo_children()):
            w.destroy()
        self._setup(carry)
        self.log(tr("Dil değiştirildi: {0}", NAMES[code]))
        return True

    def _restore_login(self, carry):
        """After a rebuild: put the still-valid login back without touching the network."""
        self.client, self.my_username, self.my_user_id = carry["client"], carry["username"], carry["uid"]
        self.load_protected()
        self.set_account(self.my_username)
        self.lbl_login.configure(text=tr("Giriş başarılı: @{0}", self.my_username))
        for i in (1, 2, 3):
            self.nb.tab(i, state="normal")
        for tab in self.bulk_tabs:
            tab.load_protected()
            tab.enable(True)
        self.nb.select(carry.get("page", 1))
        self.load_threads()

    # ------------------------------------------------------------------ UI
    def _style(self):
        ui.apply_style(self.root)

    def button(self, parent, text, command, primary=True, danger=False, kind=None):
        """Flat themed button. kind: primary | danger | secondary | ghost | success."""
        kind = kind or ("danger" if danger else ("primary" if primary else "secondary"))
        return ui.FlatButton(parent, text, command, kind=kind)

    NAV = [(T("HESAP"), [(0, T("Giriş"), "●"), (9, T("Hesap bilgisi"), "☺")]),
           (T("DM ARAÇLARI"), [(1, T("Sohbet seç"), "✉"), (2, T("Mesajlar"), "☰"), (3, T("DM temizlik"), "⌫"),
                            (8, T("Sohbet yedekle"), "⇩")]),
           (T("TEMİZLİK ARAÇLARI"), [(4, T("Story arşivi"), "▣"), (5, T("Engeller"), "⊘"), (6, T("Beğeniler"), "♥"),
                                  (7, T("Kaydedilenler"), "⚑")])]

    def _build(self):
        ui.set_window_icon(self.root)
        self.logo = ui.logo_image()
        self.empty_hints = ui.EmptyHints(self.root)

        main = tk.Frame(self.root, bg=BG)
        self._build_log(main)
        self.nb = ui.NavNotebook(main)
        self.nb.pack(fill="both", expand=True, padx=20, pady=(20, 10))

        self.tab_login = ttk.Frame(self.nb, style="Page.TFrame", padding=(24, 18))
        self.tab_threads = ttk.Frame(self.nb, style="Page.TFrame", padding=20)
        self.tab_msgs = ttk.Frame(self.nb, style="Page.TFrame", padding=20)
        self.tab_auto = ttk.Frame(self.nb, style="Page.TFrame", padding=20)
        for page in (self.tab_login, self.tab_threads, self.tab_msgs, self.tab_auto):
            self.nb.add(page, text=str(self.nb.index("end") + 1))
        for i in (1, 2, 3):
            self.nb.tab(i, state="disabled")

        nav = [(tr(section), [(idx, tr(label), glyph) for idx, label, glyph in items]) for section, items in self.NAV]
        self.sidebar = ui.Sidebar(self.root, self.nb, nav, self.logo, app_title(), f"Instagram · v{VERSION}")
        self.sidebar.pack(side="left", fill="y")
        main.pack(side="left", fill="both", expand=True)
        self._build_sidebar_footer(self.sidebar.footer)

        self._build_login()
        self._build_threads()
        self._build_msgs()
        self._build_auto()
        # notebook pages 4..9: Story, Blocked, Likes, Saved, Backup, Account
        self.bulk_tabs = [StoryTab(self), BlockedTab(self), LikesTab(self), SavedTab(self), BackupTab(self),
                          AccountTab(self)]
        self.sidebar.refresh()

    def _build_sidebar_footer(self, f):
        row = tk.Frame(f, bg=SIDEBAR)
        row.pack(fill="x", pady=(0, 12))
        row.columnconfigure(0, weight=1, uniform="cmb")
        row.columnconfigure(1, weight=1, uniform="cmb")
        tk.Label(row, text=tr("HIZ PROFİLİ"), fg="#64748b", bg=SIDEBAR, font=(FONT, 8, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w")
        tk.Label(row, text=tr("DİL"), fg="#64748b", bg=SIDEBAR, font=(FONT, 8, "bold"), anchor="w").grid(
            row=0, column=1, sticky="w", padx=(8, 0))
        self.cmb_profile = ttk.Combobox(row, textvariable=self.var_profile_disp, state="readonly", width=8,
                                        values=[profile_label(p) for p in PROFILES])
        self.cmb_profile.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.cmb_profile.bind("<<ComboboxSelected>>", lambda e: self._profile_picked())
        self.cmb_lang = ttk.Combobox(row, textvariable=self.var_lang_disp, state="readonly", width=8,
                                     values=[name for _, name in LANGS])
        self.cmb_lang.grid(row=1, column=1, sticky="ew", pady=(4, 0), padx=(8, 0))
        self.cmb_lang.bind("<<ComboboxSelected>>", lambda e: self.change_language(
            next((c for c, n in LANGS if n == self.var_lang_disp.get()), get_language())))

        chip = tk.Frame(f, bg=SIDEBAR_HOVER)
        chip.pack(fill="x", pady=(0, 10))
        self.avatar = tk.Canvas(chip, width=38, height=38, bg=SIDEBAR_HOVER, highlightthickness=0)
        self.avatar.create_oval(2, 2, 36, 36, fill="#475569", outline="", tags="bg")
        self.avatar.create_text(19, 19, text="?", fill="white", font=(FONT, 13, "bold"), tags="ch")
        self.avatar.pack(side="left", padx=10, pady=8)
        col = tk.Frame(chip, bg=SIDEBAR_HOVER)
        col.pack(side="left", fill="x", expand=True)
        self.lbl_account = tk.Label(col, text=tr("Giriş yapılmadı"), fg="#94a3b8", bg=SIDEBAR_HOVER,
                                    font=(FONT, 10, "bold"), anchor="w")
        self.lbl_account.pack(fill="x")
        self.lbl_account_sub = tk.Label(col, text=tr("Bağlı değil"), fg="#64748b", bg=SIDEBAR_HOVER,
                                        font=(FONT, 9), anchor="w")
        self.lbl_account_sub.pack(fill="x")
        self.btn_logout = self.button(f, tr("Çıkış yap ve oturumu sil"), self.logout, kind="ghost")
        self.btn_logout.pack(fill="x")

    def set_account(self, username):
        """Update the account chip in the sidebar (username=None -> logged out)."""
        if username:
            self.lbl_account.configure(text=f"@{username}", fg="white")
            self.lbl_account_sub.configure(text=tr("● Bağlı"), fg="#4ade80")
            self.avatar.itemconfigure("bg", fill=PAC)
            self.avatar.itemconfigure("ch", text=username[:1].upper(), fill="#1f2937")
        else:
            self.lbl_account.configure(text=tr("Giriş yapılmadı"), fg="#94a3b8")
            self.lbl_account_sub.configure(text=tr("Bağlı değil"), fg="#64748b")
            self.avatar.itemconfigure("bg", fill="#475569")
            self.avatar.itemconfigure("ch", text="?", fill="white")

    LOG_TAGS = {"err": ("#f87171", ("hata", "başarısız", "silinemedi", "durduruldu", "alınamadı", "yüklenemedi",
                                     "taranamadı", "engelledi")),
                "warn": ("#fbbf24", ("uyarı", "dinlen", "mola", "iptal", "yavaş", "durdurma")),
                "ok": ("#4ade80", ("silindi", "tamam", "başarılı", "bitti", "kaydedildi", "korumaya alındı",
                                    "bulundu", "listelendi", "geri çekildi", "kaldırıldı"))}

    def _build_log(self, parent):
        logf = tk.Frame(parent, bg=BG)
        logf.pack(side="bottom", fill="x", padx=20, pady=(0, 18))
        head = tk.Frame(logf, bg=BG)
        head.pack(fill="x", pady=(0, 6))
        self.log_open = True
        self.lbl_log_toggle = tk.Label(head, text=tr("▾  Etkinlik günlüğü"), bg=BG, fg=TEXT, cursor="hand2",
                                       font=(FONT, 10, "bold"))
        self.lbl_log_toggle.pack(side="left")
        self.lbl_log_toggle.bind("<Button-1>", lambda e: self.toggle_log())
        for text, cmd in ((tr("Günlük dosyasını aç"), self.open_log_file), (tr("Temizle"), self.clear_log)):
            link = tk.Label(head, text=text, fg=ACCENT, bg=BG, cursor="hand2", font=(FONT, 9, "underline"))
            link.pack(side="right", padx=(12, 0))
            link.bind("<Button-1>", lambda e, c=cmd: c())
        ttk.Checkbutton(head, text=tr("Uyarıda uzun mola verip kendiliğinden devam et"), variable=self.var_autoresume,
                        command=self.save_settings, style="Bg.TCheckbutton").pack(side="right", padx=(0, 14))
        self.log_body = tk.Frame(logf, bg="#0b1220")
        self.log_body.pack(fill="x")
        self.txt_log = tk.Text(self.log_body, height=6, state="disabled", bg="#0b1220", fg="#e2e8f0",
                               relief="flat", font=("Consolas", 9), wrap="word", highlightthickness=0, padx=12,
                               pady=8, insertbackground="white", spacing1=1)
        sb = ttk.Scrollbar(self.log_body, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt_log.pack(side="left", fill="x", expand=True)
        self.txt_log.tag_configure("time", foreground="#64748b")
        for tag, (color, _) in self.LOG_TAGS.items():
            self.txt_log.tag_configure(tag, foreground=color)

    def toggle_log(self):
        self.log_open = not self.log_open
        if self.log_open:
            self.log_body.pack(fill="x")
            self.lbl_log_toggle.configure(text=tr("▾  Etkinlik günlüğü"))
        else:
            self.log_body.pack_forget()
            self.lbl_log_toggle.configure(text=tr("▸  Etkinlik günlüğü"))

    def clear_log(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    def _build_login(self):
        f = self.tab_login
        f.columnconfigure(0, weight=1, uniform="c")
        f.columnconfigure(2, weight=1, uniform="c")

        # ---- left: password login
        L = ttk.Frame(f, style="Card.TFrame")
        L.grid(row=0, column=0, sticky="nw")
        ttk.Label(L, text=tr("A · Şifreyle giriş"), style="H.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(L, text=tr("2 adımlı doğrulaman varsa kod soracağım."), style="Sub.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))

        ttk.Label(L, text=tr("Kullanıcı adı"), style="Card.TLabel").grid(row=2, column=0, sticky="w")
        self.var_user = tk.StringVar()
        self.ent_user = ttk.Entry(L, textvariable=self.var_user, width=30, font=("Segoe UI", 11))
        self.ent_user.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 8))

        ttk.Label(L, text=tr("Şifre"), style="Card.TLabel").grid(row=4, column=0, sticky="w")
        self.var_pass = tk.StringVar()
        self.ent_pass = ttk.Entry(L, textvariable=self.var_pass, width=30, font=("Segoe UI", 11))  # görünür
        self.ent_pass.grid(row=5, column=0, sticky="w", pady=(2, 4))
        self.var_hide = tk.BooleanVar(value=False)
        ttk.Checkbutton(L, text=tr("Gizle"), variable=self.var_hide, command=self._toggle_pass).grid(
            row=5, column=1, sticky="w", padx=8)

        self.btn_login = self.button(L, tr("Şifreyle giriş yap"), self.do_login)
        self.btn_login.grid(row=6, column=0, columnspan=2, sticky="w", pady=(14, 0))

        ttk.Separator(f, orient="vertical").grid(row=0, column=1, sticky="ns", padx=20)

        # ---- right: browser session login
        R = ttk.Frame(f, style="Card.TFrame")
        R.grid(row=0, column=2, sticky="nw")
        ttk.Label(R, text=tr("B · Tarayıcı oturumuyla giriş"), style="H.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(R, style="Sub.TLabel", wraplength=400, justify="left",
                  text=tr("Şifreyle giriş 'sürüm eski' hatası verirse bunu kullan.")).grid(row=1, column=0, sticky="w", pady=(2, 6))
        ttk.Label(R, style="Card.TLabel", wraplength=400, justify="left",
                  text=tr("1) Tarayıcıda instagram.com'a giriş yap.\n"
                       "2) F12 → Application (Uygulama) → Cookies → instagram.com\n"
                       "3) 'sessionid' değerini kopyalayıp aşağı yapıştır.")
                  ).grid(row=2, column=0, sticky="w")
        self.var_sid = tk.StringVar()
        self.ent_sid = ttk.Entry(R, textvariable=self.var_sid, width=44, show="•", font=("Segoe UI", 10))
        self.ent_sid.grid(row=3, column=0, sticky="w", pady=(10, 4))
        ttk.Label(R, style="Sub.TLabel", wraplength=380, justify="left",
                  text=tr("Bu değer şifre gibidir, kimseyle paylaşma.")).grid(row=4, column=0, sticky="w")
        self.btn_login_sid = self.button(R, tr("Oturumla giriş yap"), self.do_login_session)
        self.btn_login_sid.grid(row=5, column=0, sticky="w", pady=(10, 0))

        # ---- shared
        self.var_remember = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text=tr("Bu bilgisayarda oturumu şifreli hatırla (bir sonraki açılışta tekrar giriş gerekmesin)"),
                        variable=self.var_remember).grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 2))
        self.lbl_login = ttk.Label(f, text="", style="Card.TLabel", foreground="#444444", wraplength=820, justify="left")
        self.lbl_login.grid(row=2, column=0, columnspan=3, sticky="w")
        note = tk.Frame(f, bg="#eef2ff")
        note.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        lock = tk.Canvas(note, width=22, height=26, bg="#eef2ff", highlightthickness=0)   # drawn: an emoji font costs ~150 ms
        lock.create_arc(5, 1, 17, 15, start=0, extent=180, style="arc", outline="#3730a3", width=2)
        lock.create_line(5, 8, 5, 12, fill="#3730a3", width=2)
        lock.create_line(17, 8, 17, 12, fill="#3730a3", width=2)
        lock.create_rectangle(3, 12, 19, 24, fill="#3730a3", outline="#3730a3")
        lock.create_oval(9, 15, 13, 19, fill="#eef2ff", outline="")
        lock.pack(side="left", padx=(14, 8), pady=6)
        tk.Label(note, bg="#eef2ff", fg="#3730a3", justify="left", wraplength=780, anchor="w", font=(FONT, 9),
                 text=tr("Gizlilik: şifren diske yazılmaz. Program yalnızca Instagram sunucularına bağlanır (başka "
                      "adresler engellenir). Oturumu hatırlarsan yalnızca bu Windows hesabının açabileceği şekilde "
                      "şifrelenir.")).pack(side="left", fill="x", expand=True, pady=6, padx=(0, 14))
        self.ent_pass.bind("<Return>", lambda e: self.do_login())
        self.ent_user.bind("<Return>", lambda e: self.ent_pass.focus())
        self.ent_sid.bind("<Return>", lambda e: self.do_login_session())
        self.ent_user.focus()

    def _toggle_pass(self):
        self.ent_pass.configure(show="•" if self.var_hide.get() else "")

    def _build_threads(self):
        f = self.tab_threads
        head = ttk.Frame(f, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=tr("Mesajlarını temizlemek istediğin sohbeti seç"), style="H.TLabel").pack(side="left")
        self.btn_refresh = self.button(head, tr("Yenile"), self.load_threads, primary=False)
        self.btn_refresh.pack(side="right")

        fl = ttk.Frame(f, style="Card.TFrame")
        fl.pack(fill="x", pady=(10, 6))
        ttk.Label(fl, text=tr("Ara:"), style="Card.TLabel").pack(side="left")
        self.var_filter = tk.StringVar()
        self.var_filter.trace_add("write", lambda *a: self.render_threads())
        ttk.Entry(fl, textvariable=self.var_filter, width=30).pack(side="left", padx=8)
        ttk.Label(fl, text=tr("(kullanıcı adı veya mesaj metni)"), style="Sub.TLabel").pack(side="left")

        cols = ("who", "last")
        self.tv_threads = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse", height=6)
        self.tv_threads.heading("who", text=tr("Kişiler"), anchor="w")
        self.tv_threads.heading("last", text=tr("Son mesaj"), anchor="w")
        self.tv_threads.column("who", width=260)
        self.tv_threads.column("last", width=520)
        sb = ttk.Scrollbar(f, orient="vertical", command=self.tv_threads.yview)
        self.tv_threads.configure(yscrollcommand=sb.set)
        self.tv_threads.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.empty_hints.add(self.tv_threads, tr("Sohbetler burada listelenir."))
        self.tv_threads.bind("<Double-1>", lambda e: self.choose_thread())

        side = ttk.Frame(f, style="Card.TFrame")
        side.pack(side="left", fill="y", padx=(12, 0))
        self.btn_choose = self.button(side, tr("Bu sohbeti seç  →"), self.choose_thread)
        self.btn_choose.pack(fill="x")
        self.btn_more = self.button(side, tr("Daha fazla yükle"), self.load_more_threads, primary=False)
        self.btn_more.pack(fill="x", pady=(8, 0))

    NO_CHAT_HINT = T("Henüz sohbet seçilmedi.\nSağ üstteki 'Sohbet seç' düğmesiyle bir sohbet seç.")

    def _build_msgs(self):
        f = self.tab_msgs
        head = ttk.Frame(f, style="Card.TFrame")
        head.pack(fill="x")
        self.lbl_thread = ttk.Label(head, text=tr("Sohbet: seçilmedi"), style="H.TLabel")
        self.lbl_thread.pack(side="left")
        self.btn_del_thread = self.button(head, tr("Sohbeti komple sil"), self.delete_thread, danger=True)
        self.btn_del_thread.pack(side="right")
        self.btn_pick = self.button(head, tr("Sohbet seç  →"), lambda: self.nb.select(1), kind="secondary")
        self.btn_pick.pack(side="right", padx=(0, 8))

        row = ttk.Frame(f, style="Card.TFrame")
        row.pack(fill="x", pady=(10, 4))
        ttk.Label(row, text=tr("Kelime(ler):"), style="Card.TLabel").pack(side="left")
        self.var_kw = tk.StringVar()
        e = ttk.Entry(row, textvariable=self.var_kw, width=28)
        e.pack(side="left", padx=8)
        e.bind("<Return>", lambda ev: self.find_messages())
        ttk.Label(row, text=tr("En çok kaç mesaj:"), style="Card.TLabel").pack(side="left", padx=(8, 0))
        self.var_max = tk.IntVar(value=500)
        ttk.Spinbox(row, from_=50, to=20000, increment=50, textvariable=self.var_max, width=7).pack(side="left", padx=6)
        self.btn_find = self.button(row, tr("Yükle / Ara"), self.find_messages)
        self.btn_find.pack(side="left", padx=(10, 0))
        ttk.Label(f, style="Sub.TLabel", wraplength=860, justify="left",
                  text=tr("Sohbeti seçince mesajlar otomatik yüklenir. Gri satırlar karşı tarafındır ve geri çekilemez. "
                       "Kendi mesajlarını seçip geri çekebilir ya da 'Sohbeti komple sil' ile tüm sohbeti "
                       "gelen kutundan kaldırabilirsin. Kelime yazarsan yalnızca eşleşenler listelenir.")
                  ).pack(anchor="w", pady=(0, 8))

        # Bottom widgets are packed first (side="bottom") so the list can never push them out of view.
        self.lbl_prog = ttk.Label(f, text=self.speed_text("unsend"), style="Sub.TLabel")
        self.lbl_prog.pack(side="bottom", anchor="w")
        self.pb = ttk.Progressbar(f, mode="determinate")
        self.pb.pack(side="bottom", fill="x", pady=(10, 2))

        bar = ttk.Frame(f, style="Card.TFrame")
        bar.pack(side="bottom", fill="x", pady=(10, 0))
        self.btn_all = self.button(bar, tr("Benim mesajlarımı seç"), self.select_all, primary=False)
        self.btn_all.pack(side="left")
        self.lbl_count = ttk.Label(bar, text="", style="Card.TLabel")
        self.lbl_count.pack(side="left", padx=12)
        self.btn_stop = self.button(bar, tr("Durdur"), self.stop, primary=False)
        self.btn_stop.pack(side="right")
        self.btn_delete = self.button(bar, tr("Seçili mesajlarımı geri çek"), self.delete_selected, danger=True)
        self.btn_delete.pack(side="right", padx=8)

        mid = ttk.Frame(f, style="Card.TFrame")
        mid.pack(fill="both", expand=True)
        cols = ("time", "who", "text")
        self.tv_msgs = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended", height=5)
        self.tv_msgs.heading("time", text=tr("Tarih"), anchor="w")
        self.tv_msgs.heading("who", text=tr("Gönderen"), anchor="w")
        self.tv_msgs.heading("text", text=tr("Mesaj"), anchor="w")
        self.tv_msgs.column("time", width=140, stretch=False)
        self.tv_msgs.column("who", width=130, stretch=False)
        self.tv_msgs.column("text", width=520)
        self.tv_msgs.tag_configure("other", foreground="#9ca3af")
        self.hint_msgs = self.empty_hints.add(self.tv_msgs, tr(self.NO_CHAT_HINT))
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tv_msgs.yview)
        self.tv_msgs.configure(yscrollcommand=sb.set)
        self.tv_msgs.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tv_msgs.bind("<<TreeviewSelect>>", lambda e: self.update_count())
        self.btn_stop.configure(state="disabled")

    # -------------------------------------------------------------- plumbing
    def log(self, msg):
        stamp = datetime.now().strftime("%H:%M:%S")
        low = str(getattr(msg, "src", msg)).lower()          # keywords are Turkish: use the source text
        level = next((tag for tag, (_, words) in self.LOG_TAGS.items() if any(w in low for w in words)), None)
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"{stamp}  ", "time")
        self.txt_log.insert("end", f"{msg}\n", level or ())
        if int(self.txt_log.index("end-1c").split(".")[0]) > 1500:      # keep the widget light over long runs
            self.txt_log.delete("1.0", "301.0")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")
        self._write_log_file(f"{datetime.now():%Y-%m-%d} [{stamp}] {msg}")

    def _write_log_file(self, line):
        """Queue a line for the log file; a background thread does the (slow) disk I/O, never the UI thread."""
        self._log_q.put(line)
        if self._log_thread is None or not self._log_thread.is_alive():
            self._log_thread = threading.Thread(target=self._log_writer, daemon=True)
            self._log_thread.start()

    def _log_writer(self):
        while True:
            batch = [self._log_q.get()]
            try:
                while len(batch) < 200:
                    batch.append(self._log_q.get_nowait())
            except queue.Empty:
                pass
            try:  # persistent log file (rotated at 1 MB)
                os.makedirs(APP_DIR, exist_ok=True)
                if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 1_000_000:
                    os.replace(LOG_FILE, LOG_FILE + ".1")
                with open(LOG_FILE, "a", encoding="utf-8") as fp:
                    fp.write("".join(l.rstrip("\n") + "\n" for l in batch))
            except OSError:
                pass
            finally:
                for _ in batch:
                    self._log_q.task_done()

    def flush_log(self, timeout=5.0):
        """Wait until every queued line is on disk (used on exit and by tests)."""
        end = time.time() + timeout
        while self._log_q.unfinished_tasks and time.time() < end:
            time.sleep(0.005)

    def open_log_file(self):
        try:
            if not os.path.exists(LOG_FILE):
                self.log(tr("Günlük dosyası henüz oluşmadı."))
                return
            os.startfile(LOG_FILE)
        except OSError as e:
            self.log(tr("Günlük dosyası açılamadı: {0}", e))

    def save_settings(self):
        try:
            keep = max(0, int(self.var_keep.get()))
        except (tk.TclError, ValueError):
            keep = 20
        data = load_json(SETTINGS_FILE, {})            # keep keys other tabs / versions wrote
        data.update({"profile": self.var_profile.get(), "keep": keep, "keep_pins": self.var_keep_pins.get(),
                     "unsend_first": self.var_unsend_first.get(), "auto_resume": self.var_autoresume.get(),
                     "language": get_language()})
        for tab in self.bulk_tabs:
            if hasattr(tab, "settings"):
                data.update(tab.settings())
        save_json(SETTINGS_FILE, data)

    def saved_settings(self):
        """The persisted settings dict ({} when there is none yet)."""
        return load_json(SETTINGS_FILE, {})

    # ---- per-account "keep" lists (e.g. people who must stay blocked)
    def load_keep(self, name):
        data = load_json(KEEP_FILE, {})
        return list((data.get(self.my_user_id or "") or {}).get(name, []))

    def save_keep(self, name, ids):
        data = load_json(KEEP_FILE, {})
        acct = data.setdefault(self.my_user_id or "", {})
        acct[name] = sorted(str(x) for x in ids)
        save_json(KEEP_FILE, data)

    # ---- speed profile helpers
    NOUNS = {"unsend": T("mesaj"), "hide": T("sohbet"), "story": T("story"), "unblock": T("kişi"), "unlike": T("beğeni"),
             "unsave": T("kayıt"), "download": T("dosya")}

    def speed_text(self, kind):
        lo, hi = PROFILES[self.var_profile.get()][kind]
        return tr("Hız: {0} · her {1} arasında {2}–{3} sn", profile_label(self.var_profile.get()),
                  tr(self.NOUNS.get(kind, T("işlem"))), lo, hi)

    def est(self, n, kind):
        return fmt_duration(Pacer.estimate(self.var_profile.get(), kind, n))

    def _profile_picked(self):
        """The combobox shows translated names; the setting itself stores the (Turkish) profile id."""
        self.var_profile.set(profile_id(self.var_profile_disp.get()))
        self.on_profile_change()

    def on_profile_change(self):
        self.var_profile_disp.set(profile_label(self.var_profile.get()))
        self.save_settings()
        self.log(tr("Hız profili: {0}", profile_label(self.var_profile.get())))
        if not self.busy:
            self.lbl_prog.configure(text=self.speed_text("unsend"))
            if self.auto_threads:
                self.auto_render()
            for tab in self.bulk_tabs:
                tab.render()

    def post(self, fn):
        """Run fn on the UI thread (safe to call from workers)."""
        self.q.put(fn)

    def ask(self, fn):
        """Run a dialog on the UI thread and block the worker for the answer."""
        res = queue.Queue()

        def run():
            try:
                res.put(fn())
            except Exception:
                res.put(None)

        self.q.put(run)
        return res.get()

    def _poll(self):
        """Run queued UI callbacks for at most ~6 ms per tick, so a burst of updates from a worker can never
        freeze the window; when work is left over, come straight back on the next tick."""
        t0 = time.perf_counter()
        more = False
        try:
            while True:
                fn = self.q.get_nowait()
                try:
                    fn()
                except tk.TclError:
                    pass                               # the widget was destroyed meanwhile (e.g. language switch)
                except Exception as e:                 # noqa: BLE001 - one bad callback must never stop the loop
                    self._tk_exception(type(e), e, e.__traceback__)
                if time.perf_counter() - t0 > 0.006:
                    more = True
                    break
        except queue.Empty:
            pass
        try:
            self._poll_id = self.root.after(1 if more else self.poll_ms, self._poll)
        except tk.TclError:
            pass                                   # window already destroyed

    def set_busy(self, busy):
        self.busy = busy
        st = "disabled" if busy else "normal"
        for b in (self.btn_login, self.btn_login_sid, self.btn_refresh, self.btn_choose, self.btn_more, self.btn_find,
                  self.btn_all, self.btn_delete, self.btn_del_thread, self.btn_plan, self.btn_protect):
            b.configure(state=st)
        self.cmb_profile.configure(state="disabled" if busy else "readonly")
        self.cmb_lang.configure(state="disabled" if busy else "readonly")
        self.btn_stop.configure(state="normal" if busy else "disabled")
        self.btn_auto_stop.configure(state="normal" if busy else "disabled")
        self.btn_autorun.configure(state="disabled" if (busy or not self.auto_todo) else "normal")
        for tab in self.bulk_tabs:
            tab.on_busy(busy)

    def run_bg(self, target, *args):
        """Run a worker thread. Anything that escapes it is logged and the UI is unlocked (never stuck 'busy')."""
        def runner():
            try:
                target(*args)
            except StopRequested:
                pass
            except BaseException as e:      # noqa: BLE001 - last line of defence
                tb = traceback.format_exc()
                self.post(lambda e=e, tb=tb: self._worker_crashed(e, tb))

        threading.Thread(target=runner, daemon=True).start()

    def _worker_crashed(self, e, tb):
        self.log(tr("Beklenmeyen hata: {0}", friendly(e)))
        self._write_log_file("TRACEBACK\n" + tb)
        for bar in [self.pb, self.pb_auto] + [t.pb for t in self.bulk_tabs]:
            try:
                bar.stop()
                bar.configure(mode="determinate")
            except tk.TclError:
                pass
        self.set_busy(False)

    def _tk_exception(self, exc, val, tb):
        """Errors inside Tk callbacks: log them instead of printing to a (missing) console."""
        self.log(tr("Beklenmeyen hata: {0}", friendly(val)))
        self._write_log_file("TRACEBACK\n" + "".join(traceback.format_exception(exc, val, tb)))

    def on_close(self):
        if self.busy and not ui.askyesno(app_title(), tr("Bir işlem sürüyor. Yine de kapatılsın mı?")):
            return
        self.save_settings()
        self.flush_log(1.0)
        self.root.destroy()

    def stop(self):
        self.stop_event.set()
        self.log(tr("Durdurma isteği alındı..."))

    # ---------------------------------------------------------------- login
    def new_client(self):
        c = Client()
        c.challenge_code_handler = self._challenge_code
        c.change_password_handler = self._new_password
        return c

    def _challenge_code(self, username, choice):
        code = self.ask(lambda: ui.askstring(
            app_title(), tr("Instagram doğrulama kodu istiyor ({0}).\nGelen kodu yaz:", choice), parent=self.root))
        return (code or "").strip()

    def _new_password(self, username):
        pw = self.ask(lambda: ui.askstring(
            app_title(), tr("Instagram yeni bir şifre belirlemeni istiyor.\nYeni şifreyi yaz:"), parent=self.root))
        if not pw:
            raise RuntimeError(tr("Şifre değişikliği iptal edildi."))
        return pw

    def try_saved_session(self):
        import os
        if not os.path.exists(SESSION_FILE):
            return
        self.lbl_login.configure(text=tr("Kayıtlı oturum aranıyor..."))
        self.set_busy(True)

        def work():
            client = self.new_client()
            try:
                ok = load_session(client, SESSION_FILE)
                info = client.account_info() if ok else None
            except Exception as e:
                ok, info = False, None
                self.post(lambda: self.log(tr("Kayıtlı oturum kullanılamadı: {0}", friendly(e))))
            if ok and info:
                self.post(lambda: self.login_done(client, info))
            else:
                self.post(lambda: (self.set_busy(False), self.lbl_login.configure(text=tr("Kayıtlı oturum geçersiz, yeniden giriş yap."))))

        self.run_bg(work)

    def do_login(self):
        username = self.var_user.get().strip().lstrip("@")
        password = self.var_pass.get().strip()
        if not username or not password:
            ui.showwarning(app_title(), tr("Kullanıcı adı ve şifreyi yaz."))
            return
        remember = self.var_remember.get()
        self.set_busy(True)
        self.lbl_login.configure(text=tr("Giriş yapılıyor..."))
        self.log(tr("{0} için giriş deneniyor...", username))

        def work():
            client = self.new_client()
            try:
                try:
                    client.login(username, password)
                except TwoFactorRequired:
                    self.post(lambda: self.lbl_login.configure(text=tr("2 adımlı doğrulama kodu bekleniyor...")))
                    for attempt in range(3):
                        code = self.ask(lambda: ui.askstring(
                            tr("2 adımlı doğrulama"),
                            tr("Instagram 2 adımlı doğrulama kodunu istiyor.\n\n"
                            "Doğrulama uygulamandaki 6 haneli kodu (veya SMS / yedek kodu) yaz:"),
                            parent=self.root))
                        code = (code or "").replace(" ", "").strip()
                        if not code:
                            raise RuntimeError(tr("Doğrulama kodu girilmedi, giriş iptal edildi."))
                        try:
                            client.login(username, password, verification_code=code)
                            break
                        except Exception as e2:
                            if is_limit_error(e2) or attempt == 2:
                                raise
                            self.post(lambda: self.log(tr("Kod kabul edilmedi, tekrar dene.")))
                info = client.account_info()
                if remember:
                    saved = save_session(client, SESSION_FILE)
                    self.post(lambda: self.log(tr("Oturum şifreli kaydedildi.") if saved else tr("Oturum kaydedilemedi.")))
                self.post(lambda: self.login_done(client, info))
            except Exception as e:
                msg = friendly(e)
                self.post(lambda: (self.set_busy(False), self.lbl_login.configure(text=tr("Giriş başarısız: {0}", msg)),
                                   self.log(tr("Giriş başarısız: {0}", msg))))

        self.run_bg(work)

    def do_login_session(self):
        sid = self.var_sid.get().strip().strip('"').strip()
        if sid.lower().startswith("sessionid="):
            sid = sid.split("=", 1)[1]
        sid = sid.replace("%3A", ":")  # browsers show ':' URL-encoded in cookie values
        if len(sid) < 30 or not sid[:1].isdigit():
            ui.showwarning(app_title(), 
                app_title(), tr("Bu geçerli bir 'sessionid' değerine benzemiyor.\n"
                           "Değer uzun bir metindir ve bir sayıyla başlar (örn. 1234567890%3Aabc...)."))
            return
        remember = self.var_remember.get()
        self.set_busy(True)
        self.lbl_login.configure(text=tr("Tarayıcı oturumuyla giriş yapılıyor..."))
        self.log(tr("Tarayıcı oturumuyla giriş deneniyor..."))

        def work():
            client = self.new_client()
            try:
                client.login_by_sessionid(sid)
                info = client.account_info()
                if remember:
                    saved = save_session(client, SESSION_FILE)
                    self.post(lambda: self.log(tr("Oturum şifreli kaydedildi.") if saved else tr("Oturum kaydedilemedi.")))
                self.post(lambda: (self.var_sid.set(""), self.login_done(client, info)))
            except Exception as e:
                msg = friendly(e)
                self.post(lambda: (self.set_busy(False), self.lbl_login.configure(text=tr("Giriş başarısız: {0}", msg)),
                                   self.log(tr("Oturumla giriş başarısız: {0}", msg))))

        self.run_bg(work)

    def login_done(self, client, info):
        self.client = client
        self.my_username = info.username
        self.my_user_id = str(info.pk)
        self.load_protected()
        self.var_pass.set("")
        self.set_busy(False)
        self.set_account(self.my_username)
        self.lbl_login.configure(text=tr("Giriş başarılı: @{0}", self.my_username))
        self.log(tr("Giriş başarılı: @{0}", self.my_username))
        for i in (1, 2, 3):                 # every page is usable right after login
            self.nb.tab(i, state="normal")
        for tab in self.bulk_tabs:
            tab.load_protected()
            tab.enable(True)
        self.nb.select(1)
        self.load_threads()

    def logout(self):
        if self.busy:
            ui.showinfo(app_title(), tr("Önce süren işlemi durdur."))
            return
        wiped = wipe_session(SESSION_FILE)
        self.client = None
        self.my_username = self.my_user_id = self.thread_id = None
        self.threads = []
        self.found = {}
        self.tv_threads.delete(*self.tv_threads.get_children())
        self.tv_msgs.delete(*self.tv_msgs.get_children())
        self.lbl_thread.configure(text=tr("Sohbet: seçilmedi"))
        self.hint_msgs.configure(text=tr(self.NO_CHAT_HINT))
        self.set_account(None)
        self.lbl_login.configure(text="")
        self.auto_threads, self.auto_todo, self.protected = [], [], set()
        self.tv_auto.delete(*self.tv_auto.get_children())
        self.nb.tab(1, state="disabled")
        self.nb.tab(2, state="disabled")
        self.nb.tab(3, state="disabled")
        for tab in self.bulk_tabs:
            tab.reset()
            tab.enable(False)
        self.nb.select(0)
        self.log(tr("Çıkış yapıldı.") + (tr(" Kayıtlı oturum silindi.") if wiped else ""))

    # -------------------------------------------------------------- threads
    def _inbox(self, cursor=None):
        params = {"visual_message_return_type": "unseen", "thread_message_limit": "10",
                  "persistentBadging": "true", "limit": "20"}
        if cursor:
            params["cursor"] = cursor
        return self.client.private_request("direct_v2/inbox/", params=params)

    def load_threads(self):
        self.threads = []
        self.inbox_cursor = None
        self.fetch_threads(reset=True)

    def load_more_threads(self):
        if not self.inbox_has_more:
            ui.showinfo(app_title(), tr("Başka sohbet yok."))
            return
        self.fetch_threads(reset=False)

    def fetch_threads(self, reset):
        self.set_busy(True)
        cursor = None if reset else self.inbox_cursor
        self.log(tr("Sohbetler yükleniyor..."))

        def work():
            try:
                resp = self._inbox(cursor)
                inbox = resp.get("inbox", {})
                new = inbox.get("threads", [])
                more, cur = bool(inbox.get("has_older")), inbox.get("oldest_cursor")

                def done():
                    self.threads.extend(new)
                    self.inbox_has_more, self.inbox_cursor = more, cur
                    self.render_threads()
                    self.set_busy(False)
                    self.log(tr("{0} sohbet listelendi.", len(self.threads)))
                self.post(done)
            except Exception as e:
                msg = friendly(e)
                self.post(lambda: (self.set_busy(False), self.log(tr("Sohbetler alınamadı: {0}", msg))))

        self.run_bg(work)

    @staticmethod
    def thread_title(t):
        names = [u.get("username") for u in t.get("users", []) if u.get("username")]
        return t.get("thread_title") or ", ".join(names[:3]) or tr("Bilinmeyen")

    @staticmethod
    def thread_last(t):
        items = t.get("items") or []
        return item_label(items[0]) if items else ""

    def render_threads(self):
        flt = self.var_filter.get().strip().lower()
        self.tv_threads.delete(*self.tv_threads.get_children())
        for t in self.threads:
            title, last = self.thread_title(t), self.thread_last(t)
            if flt and flt not in title.lower() and flt not in last.lower():
                continue
            self.tv_threads.insert("", "end", iid=str(t.get("thread_id")), values=(title, last[:90]))

    def choose_thread(self):
        sel = self.tv_threads.selection()
        if not sel:
            ui.showinfo(app_title(), tr("Listeden bir sohbet seç."))
            return
        self.thread_id = sel[0]
        self.thread_name = self.tv_threads.item(sel[0], "values")[0]
        self.lbl_thread.configure(text=tr("Sohbet: {0}", self.thread_name))
        self.var_kw.set("")
        self.tv_msgs.delete(*self.tv_msgs.get_children())
        self.found = {}
        self.update_count()
        self.nb.tab(2, state="normal")
        self.nb.select(2)
        self.log(tr("Sohbet seçildi: {0}", self.thread_name))
        self.find_messages()  # load the messages right away

    # ------------------------------------------------------------- messages
    def _need_chat(self):
        """True (and a hint) when no chat is selected yet."""
        if self.thread_id:
            return False
        self.lbl_prog.configure(text=tr("Önce 'Sohbet seç' sayfasından (ya da sağ üstteki düğmeyle) bir sohbet seç."))
        return True

    def find_messages(self):
        if self.busy or self._need_chat():
            return
        self.hint_msgs.configure(text=tr("Bu sohbette (bu aramayla) mesaj bulunamadı."))
        keywords = [k.strip().lower() for k in self.var_kw.get().split(",") if k.strip()]
        try:
            max_n = max(20, int(self.var_max.get()))
        except (tk.TclError, ValueError):
            max_n = 500
        self.stop_event.clear()
        self.set_busy(True)
        self.tv_msgs.delete(*self.tv_msgs.get_children())
        self.found = {}
        self.more_older = False
        self.update_count()
        self.pb.configure(mode="indeterminate")
        self.pb.start(12)
        self.lbl_prog.configure(text=tr("Mesajlar yükleniyor..."))
        self.log(tr("Mesajlar yükleniyor") + (tr(" (kelime: {0})", ", ".join(keywords)) if keywords else "") + "...")
        thread_id = self.thread_id

        def work():
            cursor, seen, scanned, own = None, set(), 0, 0
            users = {}
            more = False
            try:
                while scanned < max_n and not self.stop_event.is_set():
                    params = {"visual_message_return_type": "unseen", "direction": "older", "limit": "20"}
                    if cursor:
                        params["cursor"] = cursor
                    resp = self.client.private_request(f"direct_v2/threads/{thread_id}/", params=params)
                    thread = resp.get("thread") or {}
                    for u in thread.get("users", []):
                        users[str(u.get("pk"))] = u.get("username")
                    items = thread.get("items", [])
                    if not items:
                        if scanned == 0:
                            keys = list(resp.keys()) if isinstance(resp, dict) else type(resp).__name__
                            self.post(lambda keys=keys: self.log(
                                tr("Instagram bu sohbetten mesaj döndürmedi (yanıt alanları: {0}).", keys)))
                        break
                    rows = []
                    for it in items:
                        iid = item_id(it)
                        if not iid or str(iid) in seen:
                            continue
                        seen.add(str(iid))
                        scanned += 1
                        mine = bool(it.get("is_sent_by_viewer")) or str(it.get("user_id")) == self.my_user_id
                        own += mine
                        if keywords and not any(k in item_text(it).lower() for k in keywords):
                            continue
                        rows.append((str(iid), it, mine))
                    self.post(lambda rows=rows, users=dict(users), n=scanned, o=own: self.add_rows(rows, users, n, o))
                    cursor = thread.get("oldest_cursor")
                    more = bool(thread.get("has_older") and cursor)
                    if not more:
                        break
                    time.sleep(random.uniform(1.0, 2.5))
                self.post(lambda: self.find_done(scanned, own, more and scanned >= max_n))
            except Exception as e:
                msg = friendly(e)
                self.post(lambda: (self.pb.stop(), self.pb.configure(mode="determinate"), self.set_busy(False),
                                   self.lbl_prog.configure(text=tr("Yükleme hatası: {0}", msg)),
                                   self.log(tr("Mesajlar yüklenemedi: {0}", msg))))

        self.run_bg(work)

    def add_rows(self, rows, users, scanned, own):
        for iid, it, mine in rows:
            who = tr("Ben") if mine else (users.get(str(it.get("user_id"))) or f"ID {it.get('user_id')}")
            self.tv_msgs.insert("", "end", iid=iid, values=(item_time(it), who, item_label(it)[:200]),
                                tags=() if mine else ("other",))
            if mine:
                self.found[iid] = it
        self.lbl_prog.configure(text=tr("Yüklenen mesaj: {0} · senin: {1}", scanned, own))
        self.update_count()

    def find_done(self, scanned, own, more_older):
        self.pb.stop()
        self.pb.configure(mode="determinate", value=0)
        self.set_busy(False)
        self.more_older = more_older
        self.select_all()
        note = tr(" Daha eski mesajlar da var: 'En çok kaç mesaj' değerini artırıp tekrar yükle.") if more_older else ""
        self.lbl_prog.configure(text=tr("{0} mesaj yüklendi, {1} tanesi senin.{2}", scanned, own, note))
        self.log(tr("Yükleme bitti: {0} mesaj, senin: {1}, listelenen: {2}.{3}", scanned, own, len(self.tv_msgs.get_children()), note))

    def select_all(self):
        self.tv_msgs.selection_set([i for i in self.tv_msgs.get_children() if i in self.found])
        self.update_count()

    def update_count(self):
        total = len(self.tv_msgs.get_children())
        mine = len(self.found)
        sel = len([i for i in self.tv_msgs.selection() if i in self.found])
        self.lbl_count.configure(text=tr("{0} seçili · {1} benim · {2} listelenen", sel, mine, total))

    # -------------------------------------------------------------- deleting
    def delete_selected(self):
        if self._need_chat():
            return
        sel = [i for i in self.tv_msgs.selection() if i in self.found]
        skipped = len(self.tv_msgs.selection()) - len(sel)
        if not sel:
            ui.showinfo(app_title(), tr("Geri çekilecek kendi mesajın seçili değil.\n"
                                           "(Karşı tarafın mesajları geri çekilemez.)"))
            return
        extra = tr("\n\n({0} seçili satır karşı tarafın olduğu için atlanacak.)", skipped) if skipped else ""
        if not ui.askyesno(app_title(), 
                app_title(),
                tr("{0} mesajın geri çekilecek (herkes için silinir, geri alınamaz).\n\n{1}. Ara sıra kısa dinlenme molaları verilir; Instagram uyarı verirse program kendiliğinden yavaşlar ya da durur.\nTahmini süre: yaklaşık {2}. Bu sürede bilgisayar uykuya geçmez, pencereyi açık bırak.{3}\n\nDevam edilsin mi?", len(sel), self.speed_text('unsend'), self.est(len(sel), 'unsend'), extra)):
            return
        self.start_unsend(sel, then_hide=False)

    def delete_thread(self):
        """Delete the whole conversation from this account's inbox (optionally unsend own messages first)."""
        if self.busy or self._need_chat():
            return
        own_ids = list(self.found.keys())
        dlg = tk.Toplevel(self.root)
        dlg.title(tr("Sohbeti komple sil"))
        dlg.configure(bg=CARD)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        ui.set_window_icon(dlg)
        result = {"go": False}
        var_unsend = tk.BooleanVar(value=False)

        ttk.Label(dlg, text=tr("“{0}” sohbeti silinecek", self.thread_name), style="H.TLabel").pack(
            anchor="w", padx=20, pady=(18, 6))
        ttk.Label(dlg, style="Card.TLabel", wraplength=460, justify="left",
                  text=tr("Sohbet, Instagram'daki 'Sil' seçeneği gibi gelen kutundan kaldırılır. Bu yalnızca SENİN "
                       "hesabındaki sohbeti siler; karşı tarafın mesajları ve senin gönderdiklerin onda kalmaya "
                       "devam eder. Geri alınamaz.")).pack(anchor="w", padx=20)
        cb = ttk.Checkbutton(
            dlg, variable=var_unsend,
            text=tr("Silmeden önce yüklenen {0} mesajımı da geri çek (karşı taraftan da kaybolur; yavaş: yaklaşık {1})", len(own_ids), self.est(len(own_ids), 'unsend')))
        cb.pack(anchor="w", padx=20, pady=(14, 0))
        if not own_ids:
            cb.state(["disabled"])
        if self.more_older:
            ttk.Label(dlg, style="Sub.TLabel", wraplength=460, justify="left",
                      text=tr("Not: daha eski mesajların da var, yalnızca yüklenenler geri çekilir.")).pack(
                anchor="w", padx=20, pady=(4, 0))

        btns = ttk.Frame(dlg, style="Card.TFrame")
        btns.pack(fill="x", padx=20, pady=18)

        def go():
            result["go"] = True
            dlg.destroy()

        self.button(btns, tr("Vazgeç"), dlg.destroy, primary=False).pack(side="right")
        self.button(btns, tr("Sohbeti sil"), go, danger=True).pack(side="right", padx=8)
        dlg.grab_set()
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dlg.winfo_height()) // 3
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.root.wait_window(dlg)
        if not result["go"]:
            return
        if var_unsend.get() and own_ids:
            self.start_unsend(own_ids, then_hide=True)
        else:
            self.start_unsend([], then_hide=True)

    def begin_run(self, status_label):
        """Call on the UI thread when a run starts: snapshot Tk settings, reset the pacing state."""
        profile = self.var_profile.get()
        self.pacer = Pacer(profile)
        self.soft_hits = 0
        self.long_rests = 0
        self.auto_resume = bool(self.var_autoresume.get())
        self._status_lbl = status_label
        return profile

    # ---- pacing helpers (worker threads only)
    def _wait(self, seconds, label):
        """Countdown that reacts to Stop. label(left) -> text. Returns False if stopped."""
        for left in range(int(seconds), 0, -1):
            if self.stop_event.is_set():
                return False
            if self._status_lbl is not None:
                self.post(lambda left=left: self._status_lbl.configure(text=label(left)))
            time.sleep(1)
        return not self.stop_event.is_set()

    def pace(self, kind, label):
        """Wait the next human-like delay. label(left, rest) -> text. False if the user stopped."""
        secs, rest = self.pacer.delay(kind)
        if rest:
            self.post(lambda: self.log(tr("Kısa dinlenme molası ({0}); Instagram'ı yormamak için.", fmt_duration(secs))))
        return self._wait(secs, lambda left: label(left, rest))

    def guarded(self, fn):
        """Run fn(). On a *soft* Instagram warning: rest, slow the pacing down and retry (up to
        MAX_SOFT_HITS-1 times per run). Hard warnings and anything else propagate."""
        net_try = 0
        while True:
            try:
                return fn()
            except Exception as e:
                if is_network_error(e):            # Wi-Fi drop / timeout: wait and retry a few times
                    if net_try >= len(NET_BACKOFF):
                        raise
                    wait, net_try = NET_BACKOFF[net_try], net_try + 1
                    self.post(lambda n=net_try, wait=wait: self.log(
                        tr("Bağlantı sorunu; {0} sonra yeniden denenecek ({1}/{2}).", fmt_duration(wait), n, len(NET_BACKOFF))))
                    if not self._wait(wait, lambda left: tr("Bağlantı bekleniyor: {0} sn sonra yeniden denenecek...", left)):
                        raise StopRequested()
                    continue
                if limit_kind(e) != "soft":
                    raise
                self.soft_hits += 1
                if self.soft_hits >= MAX_SOFT_HITS:
                    if not (self.auto_resume and self.long_rests < MAX_LONG_RESTS):
                        raise
                    # autonomous mode: the warnings keep coming -> take a long break, then carry on, slower
                    self.long_rests += 1
                    self.soft_hits = 0
                    self.pacer.slow_down()
                    rest, n = random.uniform(*LONG_REST), self.long_rests
                    self.post(lambda rest=rest, n=n: self.log(
                        tr("Instagram uyarıları sürüyor. Uzun mola: {0} ({1}/{2}); sonra daha yavaş, kendiliğinden devam edilecek.", fmt_duration(rest), n, MAX_LONG_RESTS)))
                    if not self._wait(rest, lambda left, n=n: (
                            tr("Uzun mola ({0}/{1}): {2} sonra kendiliğinden devam edilecek...", n, MAX_LONG_RESTS, fmt_duration(left)))):
                        raise StopRequested()
                    continue
                self.pacer.slow_down()
                rest = random.uniform(*SOFT_PAUSE)
                hits = self.soft_hits
                self.post(lambda hits=hits, rest=rest: self.log(
                    tr("Instagram yavaşlama uyarısı verdi ({0}/{1}). {2} dinlenilecek, sonra daha yavaş devam edilecek.", hits, (MAX_SOFT_HITS - 1), fmt_duration(rest))))
                if not self._wait(rest, lambda left: tr("Instagram uyarısı: dinleniyor, {0}:{1:02d} sonra devam edilecek...", (left // 60), (left % 60))):
                    raise StopRequested()

    def start_unsend(self, iids, then_hide):
        self.stop_event.clear()
        self.set_busy(True)
        self.pb.configure(maximum=max(len(iids), 1), value=0)
        profile = self.begin_run(self.lbl_prog)   # Tk variables are read on the UI thread only
        thread_id = self.thread_id
        items = list(iids)

        def work():
            # keep Windows awake while deleting (ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
            except Exception:
                pass
            done = failed = 0
            total = len(items)
            limit_hit = False
            hidden = None
            try:
                for n, iid in enumerate(items, 1):
                    if self.stop_event.is_set():
                        break
                    try:
                        ok = self.guarded(lambda iid=iid: self.unsend_one(thread_id, str(iid)))
                    except StopRequested:
                        break
                    except Exception as e:
                        ok = False
                        msg = friendly(e)
                        self.post(lambda msg=msg: self.log(tr("Hata: {0}", msg)))
                        if is_limit_error(e):
                            self.post(lambda: self.log(tr("Instagram sınırlama uyardı. Hesabı korumak için DURDURULDU. "
                                                       "Birkaç saat bekle.")))
                            failed += 1
                            limit_hit = True
                            break
                    if ok:
                        done += 1
                        self.found.pop(str(iid), None)
                        self.post(lambda iid=iid: self.tv_msgs.delete(iid) if self.tv_msgs.exists(iid) else None)
                    else:
                        failed += 1
                    self.post(lambda n=n: (self.pb.configure(value=n), self.update_count()))
                    self.post(lambda n=n, ok=ok: self.log(f"[{n}/{total}] {tr('geri çekildi') if ok else tr('başarısız')}"))
                    if n < total and not self.stop_event.is_set():
                        left_est = fmt_duration(Pacer.estimate(profile, "unsend", total - n) * self.pacer.mult)
                        if not self.pace("unsend", lambda left, rest, n=n, le=left_est: (
                                tr("{0}/{1} işlendi · sonraki mesaj {2} sn sonra{3} · kalan ≈ {4}", n, total, left, (tr(' (dinlenme molası)') if rest else ''), le))):
                            break
                if then_hide and not limit_hit and not self.stop_event.is_set():
                    if items:
                        time.sleep(random.uniform(3, 6))
                    try:
                        hidden = self.guarded(lambda: self.hide_thread(thread_id))
                    except StopRequested:
                        pass
                    except Exception as e:
                        hidden = False
                        msg = friendly(e)
                        self.post(lambda msg=msg: self.log(tr("Sohbet silinemedi: {0}", msg)))
            finally:
                try:
                    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
                except Exception:
                    pass
                stopped = self.stop_event.is_set()
                self.post(lambda: self.delete_done(done, failed, stopped, hidden, then_hide, thread_id))

        self.run_bg(work)

    def unsend_one(self, thread_id, msg_id):
        # 1) the library's own unsend call
        try:
            if self.client.direct_message_unsend(thread_id, msg_id):
                return True
        except Exception as e:
            if is_limit_error(e):
                raise
        # 2) raw endpoints as fallback
        data = {"_uuid": self.client.uuid, "_uid": self.my_user_id, "_csrftoken": self.client.token}
        r = self.client.private_request(f"direct_v2/threads/{thread_id}/items/{msg_id}/delete/",
                                        data=data, with_signature=False)
        if r and r.get("status") == "ok":
            return True
        r2 = self.client.private_request("direct_v2/threads/broadcast/item_unsend/",
                                         data={**data, "thread_id": thread_id, "item_id": msg_id},
                                         with_signature=False)
        return bool(r2 and r2.get("status") == "ok")

    def hide_thread(self, thread_id):
        r = self.client.private_request(
            f"direct_v2/threads/{thread_id}/hide/",
            data={"should_move_future_requests_to_spam": "false", "_uuid": self.client.uuid},
            with_signature=False)
        return bool(r and r.get("status") == "ok")

    def delete_done(self, done, failed, stopped, hidden, then_hide, thread_id):
        self.set_busy(False)
        self.update_count()
        summary = tr("Geri çekilen: {0} · başarısız: {1}", done, failed)
        if hidden:
            self.log(tr("Sohbet silindi: {0}", self.thread_name))
            self.threads = [t for t in self.threads if str(t.get("thread_id")) != str(thread_id)]
            self.render_threads()
            self.thread_id = None
            self.tv_msgs.delete(*self.tv_msgs.get_children())
            self.found = {}
            self.lbl_thread.configure(text=tr("Sohbet: seçilmedi"))
            self.hint_msgs.configure(text=tr(self.NO_CHAT_HINT))
            self.nb.select(1)
            self.lbl_prog.configure(text=tr("Sohbet silindi."))
            ui.showinfo(app_title(), tr("Sohbet silindi.\n\n{0}", summary) if done or failed else tr("Sohbet silindi."))
            return
        self.lbl_prog.configure(text=tr("Bitti · {0}", summary) + (tr(" · (durduruldu)") if stopped else ""))
        self.log(tr("İşlem bitti. {0}.", summary) + (tr(" Kullanıcı durdurdu.") if stopped else ""))
        text = summary
        if then_hide and hidden is False:
            text += tr("\n\nSohbet silinemedi (ayrıntı günlükte).")
        elif then_hide and (stopped or hidden is None):
            text += tr("\n\nİşlem tamamlanmadığı için sohbet silinmedi.")
        if stopped:
            text += tr("\n\nİşlem durduruldu; kalanlar listede duruyor.")
        ui.showinfo(app_title(), text)


    # ------------------------------------------------------ auto cleanup
    def _build_auto(self):
        f = self.tab_auto
        ttk.Label(f, text=tr("Otomatik temizlik: son sohbetler dışındakileri komple sil"), style="H.TLabel").pack(anchor="w")
        ttk.Label(f, style="Sub.TLabel", wraplength=860, justify="left",
                  text=tr("Gelen kutundaki tüm sohbetleri tarar, en son yazışılan N sohbeti korur, geri kalanını sırayla "
                       "gelen kutundan siler. Silinmesini istemediğin bir sohbete ÇİFT TIKLA: yeşil 'Korumalı' olur "
                       "(tekrar çift tıklarsan kalkar; seçimin hatırlanır).")
                  ).pack(anchor="w", pady=(2, 8))

        opts = ttk.Frame(f, style="Card.TFrame")
        opts.pack(fill="x")
        ttk.Label(opts, text=tr("Korunacak son sohbet sayısı:"), style="Card.TLabel").pack(side="left")
        ttk.Spinbox(opts, from_=0, to=500, textvariable=self.var_keep, width=5, command=self.auto_settings_changed).pack(
            side="left", padx=6)
        ttk.Checkbutton(opts, text=tr("Sabitlenmiş sohbetleri koru"), variable=self.var_keep_pins,
                        command=self.auto_settings_changed).pack(side="left", padx=12)
        ttk.Label(opts, text=tr("Ara:"), style="Card.TLabel").pack(side="left", padx=(6, 0))
        ent = ttk.Entry(opts, textvariable=self.var_auto_filter, width=16)
        ent.pack(side="left", padx=4)
        self.var_auto_filter.trace_add("write", lambda *a: self.auto_render())
        self.btn_plan = self.button(opts, tr("Sohbetleri tara ve planla"), self.auto_scan)
        self.btn_plan.pack(side="right")

        ttk.Checkbutton(f, variable=self.var_unsend_first, command=self.save_settings,
                        text=tr("Silmeden önce her sohbette kendi mesajlarımı da geri çek (karşı taraftan da kaybolur; "
                             "ÇOK yavaş)")).pack(anchor="w", pady=(6, 8))

        # Bottom widgets first so the list can never push them out of view.
        self.lbl_auto = ttk.Label(f, text=tr("Önce 'Sohbetleri tara ve planla' düğmesine bas."), style="Sub.TLabel")
        self.lbl_auto.pack(side="bottom", anchor="w")
        self.pb_auto = ttk.Progressbar(f, mode="determinate")
        self.pb_auto.pack(side="bottom", fill="x", pady=(10, 2))
        bar = ttk.Frame(f, style="Card.TFrame")
        bar.pack(side="bottom", fill="x", pady=(10, 0))
        self.lbl_plan = ttk.Label(bar, text="", style="Card.TLabel")
        self.lbl_plan.pack(side="left")
        self.btn_auto_stop = self.button(bar, tr("Durdur"), self.stop, primary=False)
        self.btn_auto_stop.pack(side="right")
        self.btn_autorun = self.button(bar, tr("Otomatik temizliği başlat"), self.auto_start, danger=True)
        self.btn_autorun.pack(side="right", padx=8)
        self.btn_protect = self.button(bar, tr("Koru / korumayı kaldır"), self.toggle_protect, primary=False)
        self.btn_protect.pack(side="right")

        mid = ttk.Frame(f, style="Card.TFrame")
        mid.pack(fill="both", expand=True)
        self.tv_auto = ttk.Treeview(mid, columns=("status", "who", "last"), show="headings", selectmode="browse",
                                    height=5)
        self.tv_auto.heading("status", text=tr("Durum"), anchor="w")
        self.tv_auto.heading("who", text=tr("Kişiler"), anchor="w")
        self.tv_auto.heading("last", text=tr("Son etkinlik"), anchor="w")
        self.tv_auto.column("status", width=130, stretch=False)
        self.tv_auto.column("who", width=360)
        self.tv_auto.column("last", width=150, stretch=False)
        self.tv_auto.tag_configure("keep", foreground="#16a34a")
        self.tv_auto.tag_configure("prot", foreground="#166534", background="#dcfce7")
        self.tv_auto.tag_configure("del", foreground=TEXT)
        self.tv_auto.tag_configure("done", foreground="#9ca3af")
        self.empty_hints.add(self.tv_auto, tr("Sohbetleri taramak için yukarıdaki düğmeye bas.\nSonra silinecekleri görürsün."))
        self.tv_auto.tag_configure("err", foreground=DANGER)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tv_auto.yview)
        self.tv_auto.configure(yscrollcommand=sb.set)
        self.tv_auto.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tv_auto.bind("<Double-1>", self._auto_dblclick)
        self.tv_auto.bind("<space>", lambda e: self.toggle_protect())
        self.btn_auto_stop.configure(state="disabled")
        self.btn_autorun.configure(state="disabled")

    @staticmethod
    def thread_time(t):
        try:
            return datetime.fromtimestamp(int(t.get("last_activity_at")) / 1_000_000).strftime("%d.%m.%Y %H:%M")
        except Exception:
            return ""

    # ---- protected ("never delete") chats
    def load_protected(self):
        data = load_json(PROTECTED_FILE, {})
        self.protected = set(str(x) for x in data.get(self.my_user_id or "", []))

    def save_protected(self):
        data = load_json(PROTECTED_FILE, {})
        data[self.my_user_id or ""] = sorted(self.protected)
        save_json(PROTECTED_FILE, data)

    def _auto_dblclick(self, event):
        iid = self.tv_auto.identify_row(event.y)
        if iid:
            self.toggle_protect(iid)
        return "break"

    def toggle_protect(self, tid=None):
        if self.busy:
            return
        if tid is None:
            sel = self.tv_auto.selection()
            if not sel:
                self.lbl_auto.configure(text=tr("Önce listeden bir sohbet seç (ya da çift tıkla)."))
                return
            tid = sel[0]
        tid = str(tid)
        if tid in self.protected:
            self.protected.discard(tid)
            self.log(tr("Koruma kaldırıldı: {0}", self._title_of(tid)))
        else:
            self.protected.add(tid)
            self.log(tr("Korumaya alındı: {0}", self._title_of(tid)))
        self.save_protected()
        self.auto_render(select=tid)

    def _title_of(self, tid):
        for t in self.auto_threads:
            if str(t.get("thread_id")) == tid:
                return self.thread_title(t)
        return tid

    def auto_settings_changed(self):
        self.save_settings()
        self.auto_render()

    # ---- scan / plan
    def auto_scan(self):
        """Load EVERY inbox thread (paged), then build the keep/delete plan."""
        if self.busy:
            return
        self.stop_event.clear()
        self.set_busy(True)
        self.auto_threads, self.auto_todo = [], []
        self.tv_auto.delete(*self.tv_auto.get_children())
        self.pb_auto.configure(mode="indeterminate")
        self.pb_auto.start(12)
        self.lbl_auto.configure(text=tr("Tüm sohbetler taranıyor..."))
        self.log(tr("Otomatik temizlik: tüm sohbetler taranıyor..."))

        def work():
            found, seen, cursor = [], set(), None
            try:
                while not self.stop_event.is_set():
                    inbox = self.guarded(lambda c=cursor: self._inbox(c)).get("inbox", {})
                    for t in inbox.get("threads", []):
                        tid = str(t.get("thread_id"))
                        if tid not in seen:
                            seen.add(tid)
                            found.append(t)
                    self.post(lambda n=len(found): self.lbl_auto.configure(text=tr("Taranan sohbet: {0}", n)))
                    cursor = inbox.get("oldest_cursor")
                    if not inbox.get("has_older") or not cursor:
                        break
                    time.sleep(random.uniform(1.0, 2.5))
                self.post(lambda: self.auto_scan_done(found, self.stop_event.is_set()))
            except StopRequested:
                self.post(lambda: self.auto_scan_done([], True))
            except Exception as e:
                msg = friendly(e)
                self.post(lambda: (self.pb_auto.stop(), self.pb_auto.configure(mode="determinate"),
                                   self.set_busy(False), self.lbl_auto.configure(text=tr("Tarama hatası: {0}", msg)),
                                   self.log(tr("Sohbetler taranamadı: {0}", msg))))

        self.begin_run(self.lbl_auto)
        self.run_bg(work)

    def auto_scan_done(self, found, stopped):
        self.pb_auto.stop()
        self.pb_auto.configure(mode="determinate", value=0)
        # newest activity first (Instagram already returns them so, but do not rely on it)
        found.sort(key=lambda t: int(t.get("last_activity_at") or 0), reverse=True)
        self.auto_threads = found
        self.set_busy(False)
        if stopped:
            self.auto_threads = []
            self.lbl_auto.configure(text=tr("Tarama durduruldu."))
            return
        self.log(tr("{0} sohbet bulundu.", len(found)))
        self.auto_render()

    def auto_plan(self):
        """-> (keep, todo, reason) ; reason[thread_id] in {'manual','auto','pin'} for kept threads."""
        try:
            keep_n = max(0, int(self.var_keep.get()))
        except (tk.TclError, ValueError):
            keep_n = 20
        keep_pins = self.var_keep_pins.get()
        keep, todo, reason = [], [], {}
        for i, t in enumerate(self.auto_threads):
            tid = str(t.get("thread_id"))
            if tid in self.protected:
                reason[tid] = "manual"
            elif i < keep_n:
                reason[tid] = "auto"
            elif keep_pins and t.get("is_pin"):
                reason[tid] = "pin"
            else:
                todo.append(t)
                continue
            keep.append(t)
        return keep, todo, reason

    def auto_render(self, select=None):
        if self.busy:
            return
        pos = self.tv_auto.yview()[0]
        self.tv_auto.delete(*self.tv_auto.get_children())
        keep, todo, reason = self.auto_plan()
        self.auto_reason = reason
        flt = self.var_auto_filter.get().strip().lower()
        for t in self.auto_threads:
            tid = str(t.get("thread_id"))
            title = self.thread_title(t)
            if flt and flt not in title.lower():
                continue
            why = reason.get(tid)
            if why == "manual":
                status, tag = tr("Korumalı ★"), "prot"
            elif why:
                status, tag = tr("Korunacak"), "keep"
            else:
                status, tag = tr("Silinecek"), "del"
            self.tv_auto.insert("", "end", iid=tid, tags=(tag,), values=(status, title, self.thread_time(t)))
        self.tv_auto.yview_moveto(pos)
        if select and self.tv_auto.exists(select):
            self.tv_auto.selection_set(select)
            self.tv_auto.see(select)
        self.auto_todo = todo
        manual = sum(1 for v in reason.values() if v == "manual")
        self.lbl_plan.configure(text=tr("{0} korunacak ({1} elle korumalı) · {2} silinecek", len(keep), manual, len(todo)))
        if todo:
            self.lbl_auto.configure(text=tr("Tahmini süre: yaklaşık {0} · {1}", self.est(len(todo), 'hide'), self.speed_text('hide')))
        else:
            self.lbl_auto.configure(text=tr("Silinecek sohbet yok.") if self.auto_threads else
                                    tr("Önce 'Sohbetleri tara ve planla' düğmesine bas."))
        self.btn_autorun.configure(state="normal" if todo else "disabled")

    def auto_start(self):
        keep, todo, _ = self.auto_plan()
        if not todo or self.busy:
            return
        unsend_first = self.var_unsend_first.get()
        extra = (tr("\n\nKendi mesajların da geri çekileceği için bu ÇOK daha uzun sürer (saatler / günler).")
                 if unsend_first else "")
        answer = ui.askstring(
            tr("Onay gerekli"),
            tr("{0} sohbet komple silinecek, {1} sohbet korunacak.\nTahmini süre (yalnızca silme): yaklaşık {2} ({3} hız).{4}\n\nBu işlem geri alınamaz. Silinen sohbetler gelen kutundan kalkar (karşı taraf kendi tarafında görmeye devam eder).\nİşlem sürerken bilgisayar uykuya geçmez; pencereyi açık bırak. Instagram uyarı verirse program kendiliğinden yavaşlar ya da durur.\n\nOnaylamak için  {5}  yaz:", len(todo), len(keep), self.est(len(todo), 'hide'),
                profile_label(self.var_profile.get()), extra, tr("SİL")), parent=self.root)
        # Turkish-safe compare (SİL / Sil / sil / SIL / sıl; or the translated word, e.g. DELETE)
        if norm_word(answer) not in {norm_word("SİL"), norm_word(tr("SİL"))}:
            self.log(tr("Otomatik temizlik onaylanmadı, iptal edildi."))
            return
        self.save_settings()
        self.auto_run(list(todo), unsend_first)

    def fetch_own_ids(self, thread_id, max_n=5000):
        """Blocking: ids of my own messages in a thread (worker threads only)."""
        ids, seen, cursor, scanned = [], set(), None, 0
        while scanned < max_n and not self.stop_event.is_set():
            params = {"visual_message_return_type": "unseen", "direction": "older", "limit": "20"}
            if cursor:
                params["cursor"] = cursor
            resp = self.guarded(lambda p=params: self.client.private_request(f"direct_v2/threads/{thread_id}/", params=p))
            thread = resp.get("thread") or {}
            items = thread.get("items", [])
            if not items:
                break
            for it in items:
                iid = item_id(it)
                if not iid or str(iid) in seen:
                    continue
                seen.add(str(iid))
                scanned += 1
                if bool(it.get("is_sent_by_viewer")) or str(it.get("user_id")) == self.my_user_id:
                    ids.append(str(iid))
            cursor = thread.get("oldest_cursor")
            if not (thread.get("has_older") and cursor):
                break
            time.sleep(random.uniform(1.0, 2.5))
        return ids

    def auto_run(self, todo, unsend_first):
        self.stop_event.clear()
        self.set_busy(True)
        total = len(todo)
        self.pb_auto.configure(maximum=total, value=0)
        profile = self.begin_run(self.lbl_auto)   # Tk variables are read on the UI thread only
        self.log(tr("Otomatik temizlik başladı ({0} hız): {1} sohbet silinecek.", self.var_profile.get(), total))

        def mark(tid, status, tag):
            if self.tv_auto.exists(tid):
                self.tv_auto.set(tid, "status", status)
                self.tv_auto.item(tid, tags=(tag,))

        def eta(n):
            return fmt_duration(Pacer.estimate(profile, "hide", total - n) * self.pacer.mult)

        def work():
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)  # keep Windows awake
            except Exception:
                pass
            deleted = failed = 0
            removed = []
            limit_hit = False
            try:
                for n, t in enumerate(todo, 1):
                    if self.stop_event.is_set():
                        break
                    tid, name = str(t.get("thread_id")), self.thread_title(t)
                    if tid in self.protected:      # safety net: never delete a protected chat
                        continue
                    self.post(lambda n=n, name=name, tid=tid: (
                        self.lbl_auto.configure(text=tr("{0}/{1} · {2} siliniyor...", n, total, name)),
                        self.tv_auto.see(tid) if self.tv_auto.exists(tid) else None))
                    ok = False
                    try:
                        if unsend_first:
                            ids = self.fetch_own_ids(tid)
                            self.post(lambda name=name, k=len(ids): self.log(tr("{0}: {1} mesaj geri çekilecek.", name, k)))
                            for k, mid in enumerate(ids, 1):
                                if self.stop_event.is_set():
                                    break
                                try:
                                    self.guarded(lambda mid=mid: self.unsend_one(tid, mid))
                                except StopRequested:
                                    raise
                                except Exception as e:
                                    if is_limit_error(e):
                                        raise
                                if k < len(ids) and not self.pace("unsend", lambda left, rest, name=name, k=k, m=len(ids), n=n: (
                                        tr("{0}/{1} · {2}: mesaj {3}/{4} işlendi · sonraki {5} sn sonra{6}", n, total, name, k, m, left, (tr(' (dinlenme molası)') if rest else '')))):
                                    break
                            if self.stop_event.is_set():
                                break
                        ok = self.guarded(lambda: self.hide_thread(tid))
                    except StopRequested:
                        break
                    except Exception as e:
                        msg = friendly(e)
                        self.post(lambda name=name, msg=msg: self.log(tr("Hata ({0}): {1}", name, msg)))
                        if is_limit_error(e):
                            limit_hit = True
                            failed += 1
                            self.post(lambda tid=tid: mark(tid, tr("Hata"), "err"))
                            self.post(lambda: self.log(tr("Instagram sınırlama uyardı. Hesabı korumak için DURDURULDU. "
                                                       "Birkaç saat sonra tekrar başlat.")))
                            break
                    if ok:
                        deleted += 1
                        removed.append(tid)
                        self.post(lambda tid=tid: mark(tid, tr("Silindi"), "done"))
                        self.post(lambda n=n, name=name: self.log(tr("[{0}/{1}] silindi: {2}", n, total, name)))
                    else:
                        failed += 1
                        self.post(lambda tid=tid: mark(tid, tr("Hata"), "err"))
                        self.post(lambda n=n, name=name: self.log(tr("[{0}/{1}] silinemedi: {2}", n, total, name)))
                    self.post(lambda n=n: self.pb_auto.configure(value=n))
                    if n < total and not self.stop_event.is_set():
                        if not self.pace("hide", lambda left, rest, n=n, e=eta(n): (
                                tr("{0}/{1} işlendi · sonraki sohbet {2} sn sonra{3} · kalan ≈ {4}", n, total, left, (tr(' (dinlenme molası)') if rest else ''), e))):
                            break
            finally:
                try:
                    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
                except Exception:
                    pass
                stopped = self.stop_event.is_set()
                self.post(lambda: self.auto_done(deleted, failed, removed, stopped, limit_hit, total))

        self.run_bg(work)

    def auto_done(self, deleted, failed, removed, stopped, limit_hit, total):
        gone = set(removed)
        self.threads = [t for t in self.threads if str(t.get("thread_id")) not in gone]
        self.auto_threads = [t for t in self.auto_threads if str(t.get("thread_id")) not in gone]
        self.render_threads()
        self.set_busy(False)
        keep, todo, self.auto_reason = self.auto_plan()
        self.auto_todo = todo
        self.btn_autorun.configure(state="normal" if todo else "disabled")
        remaining = total - deleted - failed
        summary = tr("Silinen sohbet: {0} · başarısız: {1}", deleted, failed) + (tr(" · kalan: {0}", remaining) if remaining > 0 else "")
        self.lbl_auto.configure(text=tr("Bitti · {0}", summary) + (tr(" · (durduruldu)") if stopped else ""))
        self.log(tr("Otomatik temizlik bitti. {0}.", summary) + (tr(" Kullanıcı durdurdu.") if stopped else ""))
        text = summary
        if limit_hit:
            text += tr("\n\nInstagram sınırlama uyardığı için durduruldu. Birkaç saat sonra tekrar başlatabilirsin.")
        elif stopped or remaining > 0:
            text += tr("\n\nİşlem tamamlanmadı. 'Sohbetleri tara ve planla' ile yeniden tarayıp devam edebilirsin.")
        ui.showinfo(app_title(), text)


def main():
    """Start the app through the launcher (intro screen + background loading)."""
    from igdm_launcher import main as launch
    launch()


if __name__ == "__main__":
    main()
