"""
igdm_bulk.py
Autonomous "scan -> plan -> confirm -> run until done" tools, one notebook tab each:

  * StoryTab   - delete archived stories older than a chosen date
  * BlockedTab - unblock every blocked account, one by one
  * LikesTab   - remove every like
  * SavedTab   - remove every saved post/reel from 'Saved'

All of them share BulkTab: paced (human-like) requests, automatic rest + slow-down when Instagram says
"please wait", hard stop on serious warnings, double-click to protect an entry, Stop button.
"""

import ctypes
import random
import re
import time
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk

import igdm_ui as ui
from igdm_common import (DANGER, ACCENT, SUCCESS, TEXT, StopRequested, Pacer, fmt_duration, friendly, is_limit_error,
                         norm_word)
from igdm_i18n import tr, T, app_title


class BulkTab:
    # ---- to be overridden -------------------------------------------------------------------------
    key = "bulk"                    # persistence key / log prefix
    nb_title = T("Araç")
    heading = ""
    blurb = ""
    kind = "unlike"                 # pacing kind (see igdm_common.PROFILES)
    columns = ()                    # ((id, heading, width), ...) after the status column
    act_label = T("İşlenecek")
    keep_label = T("Kalacak")
    done_label = T("Tamam")
    confirm_word = T("ONAY")
    scan_text = T("Tara ve planla")
    start_text = T("Başlat")
    empty_text = T("Henüz tarama yapılmadı.\nYukarıdaki düğmeyle listeyi oluştur.")
    persist = False                 # remember protected entries per account (keep.json)
    pace_between_items = True       # False when perform() paces internally
    fine_progress = False           # True when perform() reports progress itself via add_progress()

    def __init__(self, app):
        self.app = app
        cls = type(self)            # the class constants hold Turkish source keys; translate them for this instance
        for attr in ("nb_title", "heading", "blurb", "act_label", "keep_label", "done_label", "confirm_word",
                     "scan_text", "start_text", "empty_text", "scanned_label"):
            if hasattr(cls, attr):
                setattr(self, attr, tr(getattr(cls, attr)))
        self.columns = tuple((cid, tr(head), width) for cid, head, width in cls.columns)
        self.frame = ttk.Frame(app.nb, style="Page.TFrame", padding=20)
        self.items = []             # every scanned entry: {"id", "cols", "search", ...}
        self.todo = []
        self.protected = set()
        self.done_units = 0
        self._build()
        app.nb.add(self.frame, text=self.nb_title)
        self.nb_index = app.nb.index(self.frame)
        app.nb.tab(self.nb_index, state="disabled")

    # ---- hooks --------------------------------------------------------------------------------
    def build_options(self, opts):
        """Add extra widgets to the options row (left of the scan button)."""

    def scan_items(self):
        """Worker thread: return the list of entries. Use self.status(text) for progress."""
        raise NotImplementedError

    def is_action(self, item):
        return True

    def perform(self, item):
        """Worker thread: do the work for one entry. Return True on success. May raise."""
        raise NotImplementedError

    def weight(self, item):
        return 1

    def confirm_text(self, n_act, n_keep):
        return tr("{0} kayıt işlenecek, {1} kayıt korunacak.", n_act, n_keep)

    def item_title(self, item):
        return str(item["cols"][0])

    # ---- UI -----------------------------------------------------------------------------------
    def _build(self):
        f, app = self.frame, self.app
        ttk.Label(f, text=self.heading, style="H.TLabel").pack(anchor="w")
        ttk.Label(f, style="Sub.TLabel", wraplength=860, justify="left", text=self.blurb).pack(anchor="w", pady=(2, 8))

        opts = ttk.Frame(f, style="Card.TFrame")
        opts.pack(fill="x", pady=(0, 8))
        self.build_options(opts)
        self.btn_scan = app.button(opts, self.scan_text, self.scan)
        self.btn_scan.pack(side="right")
        self.var_filter = tk.StringVar()
        ent = ttk.Entry(opts, textvariable=self.var_filter, width=16)
        ent.pack(side="right", padx=(0, 10))
        ttk.Label(opts, text=tr("Ara:"), style="Card.TLabel").pack(side="right", padx=(0, 4))
        self.var_filter.trace_add("write", lambda *a: self.render())

        # Bottom widgets first so the list can never push them out of view.
        self.lbl_status = ttk.Label(f, text=tr("Önce tara düğmesine bas."), style="Sub.TLabel")
        self.lbl_status.pack(side="bottom", anchor="w")
        self.pb = ttk.Progressbar(f, mode="determinate")
        self.pb.pack(side="bottom", fill="x", pady=(10, 2))
        bar = ttk.Frame(f, style="Card.TFrame")
        bar.pack(side="bottom", fill="x", pady=(10, 0))
        self.lbl_plan = ttk.Label(bar, text="", style="Card.TLabel")
        self.lbl_plan.pack(side="left")
        self.btn_stop = app.button(bar, tr("Durdur"), app.stop, primary=False)
        self.btn_stop.pack(side="right")
        self.btn_start = app.button(bar, self.start_text, self.start, danger=True)
        self.btn_start.pack(side="right", padx=8)
        self.btn_protect = app.button(bar, tr("Koru / korumayı kaldır"), self.toggle_protect, primary=False)
        self.btn_protect.pack(side="right")

        mid = ttk.Frame(f, style="Card.TFrame")
        mid.pack(fill="both", expand=True)
        cols = ("status",) + tuple(c[0] for c in self.columns)
        self.tv = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse", height=5)
        self.tv.heading("status", text=tr("Durum"), anchor="w")
        self.tv.column("status", width=150, stretch=False)
        for cid, head, width in self.columns:
            self.tv.heading(cid, text=head, anchor="w")
            self.tv.column(cid, width=width, stretch=(cid == self.columns[-1][0]))
        self.tv.tag_configure("act", foreground=TEXT)
        self.tv.tag_configure("keep", foreground=SUCCESS)
        self.tv.tag_configure("prot", foreground="#166534", background="#dcfce7")
        self.tv.tag_configure("done", foreground="#9ca3af")
        self.tv.tag_configure("err", foreground=DANGER)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        app.empty_hints.add(self.tv, self.empty_text)
        self.tv.bind("<Double-1>", self._dblclick)
        self.tv.bind("<space>", lambda e: self.toggle_protect())
        self.btn_stop.configure(state="disabled")
        self.btn_start.configure(state="disabled")

    # ---- app integration ----------------------------------------------------------------------
    def enable(self, on):
        self.app.nb.tab(self.nb_index, state="normal" if on else "disabled")

    def on_busy(self, busy):
        st = "disabled" if busy else "normal"
        self.btn_scan.configure(state=st)
        self.btn_protect.configure(state=st)
        self.btn_stop.configure(state="normal" if busy else "disabled")
        self.btn_start.configure(state="disabled" if (busy or not self.todo) else "normal")

    def reset(self):
        self.items, self.todo, self.protected = [], [], set()
        self.tv.delete(*self.tv.get_children())
        self.lbl_plan.configure(text="")
        self.lbl_status.configure(text=tr("Önce tara düğmesine bas."))
        self.btn_start.configure(state="disabled")

    def load_protected(self):
        if self.persist:
            self.protected = set(str(x) for x in self.app.load_keep(self.key))

    def status(self, text):
        self.app.post(lambda: self.lbl_status.configure(text=text))

    # ---- scan / plan --------------------------------------------------------------------------
    def scan(self):
        app = self.app
        if app.busy:
            return
        app.stop_event.clear()
        app.set_busy(True)
        self.items, self.todo = [], []
        self.tv.delete(*self.tv.get_children())
        self.pb.configure(mode="indeterminate")
        self.pb.start(12)
        self.lbl_status.configure(text=tr("Taranıyor..."))
        app.log(tr("{0}: tarama başladı.", self.nb_title))
        app.begin_run(self.lbl_status)

        def work():
            try:
                found = self.scan_items()
                self.app.post(lambda: self.scan_done(found, self.app.stop_event.is_set()))
            except StopRequested:
                self.app.post(lambda: self.scan_done([], True))
            except Exception as e:
                msg = friendly(e)
                self.app.post(lambda: (self.pb.stop(), self.pb.configure(mode="determinate"), app.set_busy(False),
                                       self.lbl_status.configure(text=tr("Tarama hatası: {0}", msg)),
                                       app.log(tr("{0}: tarama hatası: {1}", self.nb_title, msg))))

        app.run_bg(work)

    def scan_done(self, found, stopped):
        self.pb.stop()
        self.pb.configure(mode="determinate", value=0)
        self.items = [] if stopped else found
        self.app.set_busy(False)
        if stopped:
            self.lbl_status.configure(text=tr("Tarama durduruldu."))
            return
        self.app.log(tr("{0}: {1} kayıt bulundu.", self.nb_title, len(found)))
        self.render()

    def plan(self):
        return [it for it in self.items if self.is_action(it) and it["id"] not in self.protected]

    def render(self, select=None):
        if self.app.busy:
            return
        pos = self.tv.yview()[0]
        self.tv.delete(*self.tv.get_children())
        self.todo = self.plan()
        act_ids = {it["id"] for it in self.todo}
        flt = self.var_filter.get().strip().lower()
        for it in self.items:
            if flt and flt not in it.get("search", "").lower():
                continue
            iid = it["id"]
            if iid in self.protected:
                status, tag = tr("Korumalı ★"), "prot"
            elif iid in act_ids:
                status, tag = self.act_label, "act"
            else:
                status, tag = self.keep_label, "keep"
            self.tv.insert("", "end", iid=iid, tags=(tag,), values=(status,) + tuple(it["cols"]))
        self.tv.yview_moveto(pos)
        if select and self.tv.exists(select):
            self.tv.selection_set(select)
            self.tv.see(select)
        n_keep = len(self.items) - len(self.todo)
        units = sum(self.weight(it) for it in self.todo)
        self.lbl_plan.configure(text=tr("{0} işlenecek · {1} korunacak/kalacak", len(self.todo), n_keep))
        if self.todo:
            self.lbl_status.configure(text=tr("Tahmini süre: yaklaşık {0} · {1}", self.app.est(units, self.kind), self.app.speed_text(self.kind)))
        else:
            self.lbl_status.configure(text=tr("İşlenecek kayıt yok.") if self.items else tr("Önce tara düğmesine bas."))
        self.btn_start.configure(state="normal" if self.todo else "disabled")

    # ---- protection (double click) ------------------------------------------------------------
    def _dblclick(self, event):
        iid = self.tv.identify_row(event.y)
        if iid:
            self.toggle_protect(iid)
        return "break"

    def toggle_protect(self, iid=None):
        if self.app.busy:
            return
        if iid is None:
            sel = self.tv.selection()
            if not sel:
                self.lbl_status.configure(text=tr("Önce listeden bir kayıt seç (ya da çift tıkla)."))
                return
            iid = sel[0]
        iid = str(iid)
        if iid in self.protected:
            self.protected.discard(iid)
        else:
            self.protected.add(iid)
        if self.persist:
            self.app.save_keep(self.key, self.protected)
        self.render(select=iid)

    # ---- run ----------------------------------------------------------------------------------
    def start(self):
        if not self.todo or self.app.busy:
            return
        n_keep = len(self.items) - len(self.todo)
        units = sum(self.weight(it) for it in self.todo)
        answer = ui.askstring(
            tr("Onay gerekli"),
            tr("{0}\n\nTahmini süre: yaklaşık {1} ({2} hız). İşlem yavaş ve kendiliğinden ilerler; bilgisayar uykuya geçmez, pencereyi açık bırak. Instagram uyarı verirse program kendiliğinden yavaşlar, dinlenir ya da durur.\n\nOnaylamak için  {3}  yaz:", self.confirm_text(len(self.todo), n_keep), self.app.est(units, self.kind), self.app.var_profile.get(), self.confirm_word), parent=self.app.root)
        if norm_word(answer) not in {norm_word(self.confirm_word), norm_word(type(self).confirm_word)}:   # translated or source word
            self.app.log(tr("{0}: onaylanmadı, iptal edildi.", self.nb_title))
            return
        self.app.save_settings()
        self.run(list(self.todo))

    def add_progress(self, units):
        self.done_units += units
        v = self.done_units
        self.app.post(lambda: self.pb.configure(value=v))

    def mark(self, iid, status, tag):
        if self.tv.exists(iid):
            self.tv.set(iid, "status", status)
            self.tv.item(iid, tags=(tag,))

    def run(self, todo):
        app = self.app
        app.stop_event.clear()
        app.set_busy(True)
        total = len(todo)
        units_total = sum(self.weight(it) for it in todo)
        self.done_units = 0
        self.pb.configure(maximum=max(units_total, 1), value=0)
        profile = app.begin_run(self.lbl_status)     # Tk variables are read on the UI thread only
        kind = self.kind
        app.log(tr("{0}: otomatik işlem başladı ({1} hız): {2} kayıt.", self.nb_title, profile, total))

        def work():
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)   # keep Windows awake
            except Exception:
                pass
            ok_n = failed = 0
            removed = []
            limit_hit = False
            remaining_units = units_total
            try:
                for n, it in enumerate(todo, 1):
                    if app.stop_event.is_set():
                        break
                    iid, title, w = it["id"], self.item_title(it), self.weight(it)
                    if iid in self.protected:          # safety net
                        continue
                    self.status(tr("{0}/{1} · {2} işleniyor...", n, total, title))
                    app.post(lambda iid=iid: self.tv.see(iid) if self.tv.exists(iid) else None)
                    ok = False
                    try:
                        ok = bool(app.guarded(lambda it=it: self.perform(it)))
                    except StopRequested:
                        break
                    except Exception as e:
                        msg = friendly(e)
                        app.post(lambda title=title, msg=msg: app.log(tr("Hata ({0}): {1}", title, msg)))
                        if is_limit_error(e):
                            limit_hit = True
                            failed += 1
                            app.post(lambda iid=iid: self.mark(iid, tr("Hata"), "err"))
                            app.post(lambda: app.log(tr("Instagram sınırlama uyardı. Hesabı korumak için DURDURULDU. "
                                                     "Birkaç saat sonra tekrar başlat.")))
                            break
                    if ok:
                        ok_n += 1
                        removed.append(iid)
                        app.post(lambda iid=iid: self.mark(iid, self.done_label, "done"))
                    else:
                        failed += 1
                        app.post(lambda iid=iid: self.mark(iid, tr("Hata"), "err"))
                    remaining_units -= w
                    if not self.fine_progress:
                        self.add_progress(w)
                    app.post(lambda n=n, title=title, ok=ok: app.log(
                        f"[{n}/{total}] {'tamam' if ok else tr('başarısız')}: {title}"))
                    if self.pace_between_items and n < total and not app.stop_event.is_set():
                        eta = fmt_duration(Pacer.estimate(profile, kind, max(remaining_units, 0)) * app.pacer.mult)
                        if not app.pace(kind, lambda left, rest, n=n, eta=eta: (
                                tr("{0}/{1} işlendi · sonraki {2} sn sonra{3} · kalan ≈ {4}", n, total, left, (tr(' (dinlenme molası)') if rest else ''), eta))):
                            break
            finally:
                try:
                    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
                except Exception:
                    pass
                app.post(lambda: self.run_done(ok_n, failed, removed, app.stop_event.is_set(), limit_hit, total))

        app.run_bg(work)

    def run_done(self, ok_n, failed, removed, stopped, limit_hit, total):
        gone = set(removed)
        self.items = [it for it in self.items if it["id"] not in gone]
        self.app.set_busy(False)
        self.todo = self.plan()
        remaining = total - ok_n - failed
        summary = tr("Başarılı: {0} · başarısız: {1}", ok_n, failed) + (tr(" · kalan: {0}", remaining) if remaining > 0 else "")
        self.lbl_status.configure(text=tr("Bitti · {0}", summary) + (tr(" · (durduruldu)") if stopped else ""))
        self.btn_start.configure(state="normal" if self.todo else "disabled")
        self.app.log(tr("{0}: bitti. {1}.", self.nb_title, summary) + (tr(" Kullanıcı durdurdu.") if stopped else ""))
        text = summary
        if limit_hit:
            text += tr("\n\nInstagram sınırlama uyardığı için durduruldu. Birkaç saat sonra tekrar başlatabilirsin.")
        elif stopped or remaining > 0:
            text += tr("\n\nİşlem tamamlanmadı. Yeniden tarayıp kaldığın yerden devam edebilirsin.")
        ui.showinfo(app_title(), text)


# ======================================================================================= stories
_DATE_RE = re.compile(r"^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})\s*$")


def parse_date(text):
    """'GG.AA.YYYY' -> naive local datetime at 00:00, or None."""
    m = _DATE_RE.match(text or "")
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


class StoryTab(BulkTab):
    key = "stories"
    nb_title = T("Story arşivi")
    heading = T("Arşivlenmiş story temizleyici")
    blurb = (T("Belirlediğin tarihten ÖNCEKİ arşivlenmiş storyleri kalıcı olarak siler. Arşivi tarar, gün gün listeler; "
             "silinmesini istemediğin bir güne ÇİFT TIKLA (yeşil 'Korumalı' olur). Silinen story geri getirilemez."))
    kind = "story"
    columns = (("date", T("Gün"), 200), ("count", T("Story sayısı"), 120))
    act_label = T("Silinecek")
    keep_label = T("Kalacak")
    done_label = T("Silindi")
    confirm_word = T("SİL")
    scan_text = T("Arşivi tara ve planla")
    start_text = T("Eski storyleri sil")
    pace_between_items = False      # perform() paces between the individual stories
    fine_progress = True

    def build_options(self, opts):
        ttk.Label(opts, text=tr("Şu tarihten önce (GG.AA.YYYY):"), style="Card.TLabel").pack(side="left")
        self.var_date = tk.StringVar(value=(datetime.now() - timedelta(days=30)).strftime("%d.%m.%Y"))
        ent = ttk.Entry(opts, textvariable=self.var_date, width=11)
        ent.pack(side="left", padx=6)
        ent.bind("<Return>", lambda e: self.render())
        ent.bind("<FocusOut>", lambda e: self.render())
        for label, days in ((tr("1 ay"), 30), (tr("6 ay"), 182), (tr("1 yıl"), 365)):
            b = tk.Label(opts, text=label + tr(" önce"), fg=ACCENT, bg="white", cursor="hand2",
                         font=("Segoe UI", 9, "underline"))
            b.pack(side="left", padx=4)
            b.bind("<Button-1>", lambda e, d=days: self.set_days(d))
        ttk.Label(opts, text=tr("(GG.AA.YYYY)"), style="Sub.TLabel").pack(side="left", padx=4)

    def set_days(self, days):
        self.var_date.set((datetime.now() - timedelta(days=days)).strftime("%d.%m.%Y"))
        self.render()

    def cutoff(self):
        return parse_date(self.var_date.get())

    def is_action(self, item):
        cut = self.cutoff()
        return cut is not None and item["ts"] < cut

    def render(self, select=None):
        super().render(select)
        if not self.app.busy and self.items and self.cutoff() is None:
            self.lbl_status.configure(text=tr("Tarih geçersiz. GG.AA.YYYY biçiminde yaz (örn. 01.03.2025)."))

    def weight(self, item):
        return max(1, int(item.get("count") or 1))

    def confirm_text(self, n_act, n_keep):
        units = sum(self.weight(it) for it in self.todo)
        return (tr("{0:%d.%m.%Y} tarihinden önceki {1} güne ait yaklaşık {2} arşivlenmiş story KALICI olarak silinecek ({3} gün kalacak). Bu işlem geri alınamaz.", self.cutoff(), n_act, units, n_keep))

    def scan_items(self):
        client, app = self.app.client, self.app
        days, cursor, seen = [], "", set()
        while not app.stop_event.is_set():
            page, nxt = app.guarded(lambda c=cursor: client.archive_story_days_paginated_v1(
                end_cursor=c, include_memories=False))
            for d in page:
                if d.id in seen:
                    continue
                seen.add(d.id)
                ts = d.timestamp
                if getattr(ts, "tzinfo", None):
                    ts = ts.astimezone().replace(tzinfo=None)
                days.append({"id": str(d.id), "ts": ts, "count": d.media_count,
                             "cols": (ts.strftime("%d.%m.%Y"), d.media_count),
                             "search": ts.strftime("%d.%m.%Y")})
            self.status(tr("Taranan gün: {0}", len(days)))
            if not nxt or nxt == cursor or not page:
                break
            cursor = nxt
            time.sleep(random.uniform(1.0, 2.5))
        days.sort(key=lambda x: x["ts"], reverse=True)
        return days

    def item_title(self, item):
        return tr("{0} ({1} story)", item["cols"][0], item.get("count", "?"))

    def perform(self, day):
        app, client = self.app, self.app.client
        data = client.with_default_data({"reel_ids": [day["id"]], "reason": "on_tap", "source": "archive",
                                         "batch_size": 1})
        result = client.private_request("feed/reels_media_stream/", data=data)   # run() already wraps perform()
        pks = []
        for reel in client._archive_story_reels(result):
            for it in reel.get("items", []):
                pk = it.get("pk") or it.get("id")
                if pk:
                    pks.append(str(pk).split("_")[0])
        if not pks:
            self.add_progress(self.weight(day))     # nothing left in that day
            return True
        okay = True
        for k, pk in enumerate(pks, 1):
            if app.stop_event.is_set():
                raise StopRequested()
            if self.delete_story(pk):
                self.add_progress(1)
            else:
                okay = False
            if k < len(pks) and not app.pace(
                    "story", lambda left, rest, k=k, m=len(pks), t=day["cols"][0]: (
                        tr("{0}: story {1}/{2} işlendi · sonraki {3} sn sonra{4}", t, k, m, left, (tr(' (dinlenme molası)') if rest else '')))):
                raise StopRequested()
        return okay

    def delete_story(self, pk):
        client = self.app.client
        try:
            if client.story_delete(pk):
                return True
        except Exception as e:
            if is_limit_error(e):
                raise
        mid = client.media_id(pk)
        r = client.private_request(f"media/{mid}/delete/?media_type=STORY",
                                   client.with_default_data({"media_id": mid}))
        return bool(r.get("did_delete"))


# ======================================================================================== blocked
class BlockedTab(BulkTab):
    key = "blocked"
    nb_title = T("Engeller")
    heading = T("Engellenen hesapların engelini otomatik kaldır")
    blurb = (T("Engellediğin tüm hesapları listeler ve engellerini tek tek, yavaşça kaldırır. Engelli KALMASINI istediğin "
             "kişiye ÇİFT TIKLA: yeşil 'Korumalı' olur ve bu seçim hatırlanır. Engeli kalkan kişi profilini yeniden "
             "görebilir ve seni takip etmeyi deneyebilir."))
    kind = "unblock"
    columns = (("user", T("Kullanıcı adı"), 200), ("name", T("Ad"), 220), ("when", T("Engellendiği tarih"), 150))
    act_label = T("Engeli kalkacak")
    keep_label = T("Engelli kalacak")
    done_label = T("Engeli kalktı")
    confirm_word = T("KALDIR")
    scan_text = T("Engelleri tara ve planla")
    start_text = T("Engelleri kaldır")
    persist = True

    def confirm_text(self, n_act, n_keep):
        return (tr("{0} hesabın engeli kaldırılacak, {1} hesap engelli kalacak. Engellediğin kişiler (taciz eden ya da istemediğin hesaplar dahil) seni yeniden görebilecek.", n_act, n_keep))

    def scan_items(self):
        client, app = self.app.client, self.app
        found, cursor, seen = [], "", set()
        while not app.stop_event.is_set():
            params = {"max_id": cursor} if cursor else None
            res = app.guarded(lambda p=params: client.private_request("users/blocked_list/", params=p))
            page = res.get("blocked_list") or []
            for u in page:
                uid = str(u.get("user_id") or u.get("pk") or "")
                if not uid or uid in seen:
                    continue
                seen.add(uid)
                try:
                    when = datetime.fromtimestamp(int(u.get("block_at"))).strftime("%d.%m.%Y")
                except (TypeError, ValueError, OSError):
                    when = ""
                uname = u.get("username") or uid
                found.append({"id": uid, "cols": (uname, u.get("full_name") or "", when),
                              "search": f"{uname} {u.get('full_name') or ''}"})
            self.status(tr("Taranan engelli hesap: {0}", len(found)))
            nxt = res.get("next_max_id") or ""
            if not page or not nxt or nxt == cursor:
                break
            cursor = nxt
            time.sleep(random.uniform(1.0, 2.5))
        return found

    def item_title(self, item):
        return "@" + str(item["cols"][0])

    def perform(self, item):
        return bool(self.app.client.user_unblock(item["id"]))


# ========================================================================================== likes / saved
_MEDIA_TYPES = {1: T("Fotoğraf"), 2: T("Video"), 8: T("Albüm")}


class MediaListTab(BulkTab):
    """Posts/reels listed by a paged feed endpoint; the action removes the like / the save."""
    endpoint = "feed/liked/"
    columns = (("owner", T("Hesap"), 150), ("type", T("Tür"), 100), ("date", T("Gönderi tarihi"), 150),
               ("text", T("Açıklama"), 300))
    scanned_label = T("Taranan kayıt")

    def scan_items(self):
        client, app = self.app.client, self.app
        found, cursor, seen, pages = [], "", set(), 0
        while not app.stop_event.is_set() and pages < 5000:
            params = {"include_igtv_preview": "false"}
            if cursor:
                params["max_id"] = cursor
            res = app.guarded(lambda p=params: client.private_request(self.endpoint, params=p))
            page = res.get("items") or []
            pages += 1
            for entry in page:
                m = entry.get("media", entry)
                mid = str(m.get("id") or m.get("pk") or "")
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                owner = (m.get("user") or {}).get("username") or ""
                kind = tr("Reel") if m.get("product_type") == "clips" else tr(_MEDIA_TYPES.get(m.get("media_type"), T("Gönderi")))
                try:
                    date = datetime.fromtimestamp(int(m.get("taken_at"))).strftime("%d.%m.%Y")
                except (TypeError, ValueError, OSError):
                    date = ""
                text = ((m.get("caption") or {}).get("text") or "").replace("\n", " ")[:120]
                found.append({"id": mid, "cols": (owner, kind, date, text), "search": f"{owner} {text}"})
            self.status(f"{self.scanned_label}: {len(found)}")
            nxt = res.get("next_max_id") or res.get("max_id") or ""
            if not page or not nxt or nxt == cursor:
                break
            cursor = nxt
            time.sleep(random.uniform(1.0, 2.5))
        return found

    def item_title(self, item):
        owner, kind = item["cols"][0], item["cols"][1]
        return f"@{owner} ({kind})" if owner else str(item["id"])


class LikesTab(MediaListTab):
    key = "likes"
    nb_title = T("Beğeniler")
    heading = T("Tüm beğenileri otomatik kaldır")
    blurb = (T("Beğendiğin tüm gönderi ve reelleri listeler, beğenilerini tek tek, yavaşça kaldırır. Beğenisi KALSIN "
             "istediğin bir gönderiye ÇİFT TIKLA (yeşil 'Korumalı' olur). Not: yorum beğenileri bu listede yer almaz."))
    kind = "unlike"
    endpoint = "feed/liked/"
    scanned_label = T("Taranan beğeni")
    act_label = T("Beğeni kalkacak")
    keep_label = T("Beğeni kalacak")
    done_label = T("Beğeni kalktı")
    confirm_word = T("KALDIR")
    scan_text = T("Beğenileri tara ve planla")
    start_text = T("Beğenileri kaldır")

    def confirm_text(self, n_act, n_keep):
        return tr("{0} gönderinin beğenisi kaldırılacak, {1} beğeni kalacak.", n_act, n_keep)

    def perform(self, item):
        return bool(self.app.client.media_unlike(item["id"]))


class SavedTab(MediaListTab):
    key = "saved"
    nb_title = T("Kaydedilenler")
    heading = T("Kaydedilen gönderi ve reelleri temizle")
    blurb = (T("Hesabında kaydettiğin (yer imi) tüm gönderi ve reelleri listeler ve kayıtlarını tek tek, yavaşça kaldırır. "
             "Kaydı KALSIN istediğin bir gönderiye ÇİFT TIKLA (yeşil 'Korumalı' olur). Gönderinin kendisi silinmez; "
             "yalnızca senin 'Kaydedilenler' listenden çıkar."))
    kind = "unsave"
    endpoint = "feed/saved/posts/"
    scanned_label = T("Taranan kayıt")
    act_label = T("Kayıt kalkacak")
    keep_label = T("Kayıt kalacak")
    done_label = T("Kayıt kalktı")
    confirm_word = T("KALDIR")
    scan_text = T("Kaydedilenleri tara ve planla")
    start_text = T("Kayıtları kaldır")

    def confirm_text(self, n_act, n_keep):
        return (tr("{0} gönderi/reel 'Kaydedilenler' listenden çıkarılacak, {1} kayıt kalacak. Gönderilerin kendisi silinmez.", n_act, n_keep))

    def perform(self, item):
        return bool(self.app.client.media_unsave(item["id"]))
