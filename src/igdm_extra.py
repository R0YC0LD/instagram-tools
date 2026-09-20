"""
igdm_extra.py
Two more pages:

  * BackupTab  - export chats one by one: <folder>/<person>/sohbet.txt plus the photos (and, optionally,
                 videos / voice messages) that were sent in that chat.
  * AccountTab - read-only account overview (profile numbers, when the account was created, ...).

Both only READ from Instagram; nothing is deleted or changed.
"""

import os
import random
import re
import time
from datetime import datetime
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, filedialog

import igdm_ui as ui
from igdm_common import (DANGER, SUCCESS, PROFILES, StopRequested, friendly, is_limit_error, limit_kind)
from igdm_items import item_id, item_label, item_text
from igdm_i18n import tr, T, app_title, get_language

# =============================================================================================== helpers
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_name(name, fallback="sohbet", maxlen=80):
    """A string that is always a valid single Windows file/folder name."""
    s = _BAD_CHARS.sub("_", (name or "").strip()).strip(" .")
    if not s:
        s = fallback
    if s.split(".")[0].upper() in _RESERVED:
        s = "_" + s
    return (s[:maxlen].rstrip(" .")) or fallback


def default_backup_dir():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), tr("Instagram Araçları"), tr("Yedekler"))


_EXT_OK = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".m4a", ".mp3", ".aac", ".mov", ".heic"}
_DEFAULT_EXT = {"image": ".jpg", "video": ".mp4", "voice": ".m4a"}


def file_ext(url, kind):
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return ext if ext in _EXT_OK else _DEFAULT_EXT[kind]


def media_refs(it):
    """Downloadable files in one direct-message item -> [(kind, url)] with kind in image / video / voice."""
    t, out = it.get("item_type"), []
    if t == "media":
        m = it.get("media") or {}
        vids = m.get("video_versions") or []
        if vids and vids[0].get("url"):
            out.append(("video", vids[0]["url"]))
        cands = (m.get("image_versions2") or {}).get("candidates") or []
        if cands and cands[0].get("url") and not vids:
            out.append(("image", cands[0]["url"]))
    elif t == "voice_media":
        url = ((((it.get("voice_media") or {}).get("media") or {}).get("audio")) or {}).get("audio_src")
        if url:
            out.append(("voice", url))
    return out


def fetch_to_file(url, path, timeout=(10, 60)):
    """Download url -> path (via a .part file). Goes through the network guard: Instagram/CDN hosts only."""
    import requests
    tmp = path + ".part"
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fp:
            for chunk in r.iter_content(65536):
                if chunk:
                    fp.write(chunk)
    os.replace(tmp, path)


def _ts(it):
    try:
        return datetime.fromtimestamp(int(it["timestamp"]) / 1_000_000)
    except Exception:
        return None


def format_message(it, sender, files):
    """One message -> text lines (first line carries the timestamp and sender)."""
    ts = _ts(it)
    stamp = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "????-??-?? ??:??:??"
    t = it.get("item_type")
    body = item_text(it)
    kind_names = {"image": tr("Fotoğraf"), "video": tr("Video"), "voice": tr("Sesli mesaj")}
    refs = media_refs(it)
    if refs:
        parts = []
        for kind, _url in refs:
            rel = files.get((item_id(it), kind))
            parts.append(f"[{kind_names[kind]}: {rel}]" if rel else f"[{kind_names[kind]}]")
        body = " ".join(parts) + (f" {body}" if body else "")
    elif not body:
        body = item_label(it)
        if t == "action_log":
            body = tr("[Sistem] {0}", (it.get("action_log") or {}).get("description", "")).rstrip()
    rx = ((it.get("reactions") or {}).get("emojis")) or []
    if rx:
        body += tr("   (tepkiler: {0})", " ".join(str(e.get("emoji", "")) for e in rx if isinstance(e, dict)))
    lines = body.replace("\r", "").split("\n")
    out = [f"[{stamp}] {sender}: {lines[0]}"]
    out += [f"{' ' * (len(stamp) + 3)}{ln}" for ln in lines[1:]]
    return out


# ============================================================================================ chat backup
class BackupTab:
    nb_title = T("Sohbet yedekle")

    def __init__(self, app):
        self.app = app
        self.frame = ttk.Frame(app.nb, style="Page.TFrame", padding=20)
        self.threads = []
        saved = app.saved_settings()
        self.var_dir = tk.StringVar(value=saved.get("backup_dir") or default_backup_dir())
        self.var_img = tk.BooleanVar(value=bool(saved.get("backup_images", True)))
        self.var_vid = tk.BooleanVar(value=bool(saved.get("backup_videos", False)))
        self.var_voice = tk.BooleanVar(value=bool(saved.get("backup_voice", False)))
        self.var_filter = tk.StringVar()
        self.last_result = None
        self._build()
        app.nb.add(self.frame, text=tr(self.nb_title))
        self.nb_index = app.nb.index(self.frame)
        app.nb.tab(self.nb_index, state="disabled")

    # ---- UI ------------------------------------------------------------------------------------
    def _build(self):
        f, app = self.frame, self.app
        ttk.Label(f, text=tr("Sohbetleri yedekle (TXT + görseller)"), style="H.TLabel").pack(anchor="w")
        ttk.Label(f, style="Sub.TLabel", wraplength=880, justify="left",
                  text=tr("Seçtiğin sohbetleri tek tek dışa aktarır. Her kişi için kendi adında bir klasör açılır: içinde "
                       "sohbetin metin dosyası (sohbet.txt) ve sohbette gönderilen görseller olur. Bu işlem yalnızca "
                       "OKUR; hiçbir şey silinmez.")).pack(anchor="w", pady=(2, 8))

        row = ttk.Frame(f, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 4))
        ttk.Label(row, text=tr("Yedek klasörü:"), style="Card.TLabel").pack(side="left")
        ent = ttk.Entry(row, textvariable=self.var_dir, width=58)
        ent.pack(side="left", padx=8, fill="x", expand=True)
        self.btn_dir = app.button(row, tr("Klasör seç…"), self.choose_folder, kind="secondary")
        self.btn_dir.pack(side="left")
        self.btn_open = app.button(row, tr("Klasörü aç"), self.open_folder, kind="secondary")
        self.btn_open.pack(side="left", padx=(8, 0))

        opts = ttk.Frame(f, style="Card.TFrame")
        opts.pack(fill="x", pady=(4, 6))
        ttk.Checkbutton(opts, text=tr("Görselleri indir"), variable=self.var_img, command=app.save_settings).pack(side="left")
        ttk.Checkbutton(opts, text=tr("Videoları indir (büyük olabilir)"), variable=self.var_vid,
                        command=app.save_settings).pack(side="left", padx=14)
        ttk.Checkbutton(opts, text=tr("Sesli mesajları indir"), variable=self.var_voice,
                        command=app.save_settings).pack(side="left")
        find = ttk.Frame(f, style="Card.TFrame")            # own row: nothing gets squeezed in any language
        find.pack(fill="x", pady=(0, 6))
        ttk.Label(find, text=tr("Ara:"), style="Card.TLabel").pack(side="left", padx=(0, 6))
        ttk.Entry(find, textvariable=self.var_filter, width=28).pack(side="left")
        self.btn_load = app.button(find, tr("Sohbetleri yükle"), self.load_chats)
        self.btn_load.pack(side="right")
        self.var_filter.trace_add("write", lambda *a: self.render())

        # Bottom widgets first so the list can never push them out of view.
        self.lbl_status = ttk.Label(f, text=tr("Önce 'Sohbetleri yükle' düğmesine bas."), style="Sub.TLabel")
        self.lbl_status.pack(side="bottom", anchor="w")
        self.pb = ttk.Progressbar(f, mode="determinate")
        self.pb.pack(side="bottom", fill="x", pady=(10, 2))
        bar = ttk.Frame(f, style="Card.TFrame")
        bar.pack(side="bottom", fill="x", pady=(10, 0))
        self.lbl_count = ttk.Label(bar, text="", style="Card.TLabel")
        self.lbl_count.pack(side="left")
        self.btn_stop = app.button(bar, tr("Durdur"), app.stop, primary=False)
        self.btn_stop.pack(side="right")
        self.btn_start = app.button(bar, tr("Seçilenleri yedekle"), self.start, kind="success")
        self.btn_start.pack(side="right", padx=8)
        self.btn_all = app.button(bar, tr("Hepsini seç"), self.select_all, kind="secondary")
        self.btn_all.pack(side="right")

        mid = ttk.Frame(f, style="Card.TFrame")
        mid.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(mid, columns=("status", "who", "last"), show="headings", selectmode="extended", height=5)
        self.tv.heading("status", text=tr("Durum"), anchor="w")
        self.tv.heading("who", text=tr("Sohbet"), anchor="w")
        self.tv.heading("last", text=tr("Son etkinlik"), anchor="w")
        self.tv.column("status", width=250, stretch=False)
        self.tv.column("who", width=340)
        self.tv.column("last", width=150, stretch=False)
        self.tv.tag_configure("done", foreground=SUCCESS)
        self.tv.tag_configure("err", foreground=DANGER)
        self.tv.tag_configure("run", foreground="#4f46e5")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        app.empty_hints.add(self.tv, tr("Henüz sohbet yüklenmedi.\nYukarıdaki düğmeyle sohbetlerini listele."))
        self.tv.bind("<<TreeviewSelect>>", lambda e: self._count())
        self.btn_stop.configure(state="disabled")
        self.btn_start.configure(state="disabled")

    # ---- app integration (same small interface the BulkTabs offer) -----------------------------------
    def enable(self, on):
        self.app.nb.tab(self.nb_index, state="normal" if on else "disabled")

    def on_busy(self, busy):
        st = "disabled" if busy else "normal"
        for b in (self.btn_dir, self.btn_load, self.btn_all):
            b.configure(state=st)
        self.btn_stop.configure(state="normal" if busy else "disabled")
        self.btn_start.configure(state="disabled" if (busy or not self.threads) else "normal")

    def reset(self):
        self.threads = []
        self.tv.delete(*self.tv.get_children())
        self.lbl_count.configure(text="")
        self.lbl_status.configure(text=tr("Önce 'Sohbetleri yükle' düğmesine bas."))
        self.btn_start.configure(state="disabled")

    def load_protected(self):
        pass

    def settings(self):
        return {"backup_dir": self.var_dir.get().strip(), "backup_images": bool(self.var_img.get()),
                "backup_videos": bool(self.var_vid.get()), "backup_voice": bool(self.var_voice.get())}

    # ---- folder ----------------------------------------------------------------------------------
    def choose_folder(self):
        d = filedialog.askdirectory(parent=self.app.root, initialdir=self.var_dir.get() or None,
                                    title=tr("Yedek klasörünü seç"))
        if d:
            self.var_dir.set(os.path.normpath(d))
            self.app.save_settings()

    def open_folder(self):
        d = self.var_dir.get().strip()
        try:
            os.makedirs(d, exist_ok=True)
            os.startfile(d)
        except OSError as e:
            self.app.log(tr("Klasör açılamadı: {0}", e))

    # ---- list ------------------------------------------------------------------------------------
    def render(self):
        if self.app.busy:
            return
        flt = self.var_filter.get().strip().lower()
        sel = set(self.tv.selection())
        self.tv.delete(*self.tv.get_children())
        for t in self.threads:
            title = self.app.thread_title(t)
            if flt and flt not in title.lower():
                continue
            tid = str(t.get("thread_id"))
            self.tv.insert("", "end", iid=tid, values=(tr("Bekliyor"), title, self.app.thread_time(t)))
        keep = [i for i in sel if self.tv.exists(i)]
        if keep:
            self.tv.selection_set(keep)
        self._count()

    def _count(self):
        self.lbl_count.configure(text=tr("{0} seçili · {1} sohbet", len(self.tv.selection()), len(self.tv.get_children())))

    def select_all(self):
        self.tv.selection_set(self.tv.get_children())
        self._count()

    def load_chats(self):
        app = self.app
        if app.busy:
            return
        app.stop_event.clear()
        app.set_busy(True)
        self.threads = []
        self.tv.delete(*self.tv.get_children())
        self.pb.configure(mode="indeterminate")
        self.pb.start(12)
        self.lbl_status.configure(text=tr("Sohbetler yükleniyor..."))
        app.begin_run(self.lbl_status)

        def work():
            found, seen, cursor = [], set(), None
            try:
                while not app.stop_event.is_set():
                    inbox = app.guarded(lambda c=cursor: app._inbox(c)).get("inbox", {})
                    for t in inbox.get("threads", []):
                        tid = str(t.get("thread_id"))
                        if tid not in seen:
                            seen.add(tid)
                            found.append(t)
                    app.post(lambda n=len(found): self.lbl_status.configure(text=tr("Yüklenen sohbet: {0}", n)))
                    cursor = inbox.get("oldest_cursor")
                    if not inbox.get("has_older") or not cursor:
                        break
                    time.sleep(random.uniform(1.0, 2.5))
                found.sort(key=lambda t: int(t.get("last_activity_at") or 0), reverse=True)
                app.post(lambda: self._loaded(found))
            except StopRequested:
                app.post(lambda: self._loaded([]))
            except Exception as e:
                msg = friendly(e)
                app.post(lambda: (self.pb.stop(), self.pb.configure(mode="determinate"), app.set_busy(False),
                                  self.lbl_status.configure(text=tr("Sohbetler yüklenemedi: {0}", msg)),
                                  app.log(tr("Sohbet yedekle: yüklenemedi: {0}", msg))))

        app.run_bg(work)

    def _loaded(self, found):
        self.pb.stop()
        self.pb.configure(mode="determinate", value=0)
        self.threads = found
        self.app.set_busy(False)
        self.render()
        self.lbl_status.configure(text=tr("{0} sohbet yüklendi. Yedeklemek istediklerini seç.", len(found)) if found
                                  else tr("Sohbet bulunamadı."))
        self.app.log(tr("Sohbet yedekle: {0} sohbet listelendi.", len(found)))

    # ---- backup ----------------------------------------------------------------------------------
    def start(self):
        app = self.app
        if app.busy:
            return
        chosen = list(self.tv.selection())
        if not chosen:
            ui.showinfo(app_title(), tr("Önce yedeklenecek sohbetleri seç.\n(Ctrl / Shift ile çoklu seçim yapabilir ya da "
                                   "'Hepsini seç' düğmesini kullanabilirsin.)"))
            return
        root_dir = self.var_dir.get().strip()
        try:
            os.makedirs(root_dir, exist_ok=True)
        except OSError as e:
            ui.showwarning(app_title(), tr("Yedek klasörü oluşturulamadı:\n{0}\n\n{1}", root_dir, e))
            return
        chosen_set = set(chosen)
        threads = [t for t in self.threads if str(t.get("thread_id")) in chosen_set]
        opts = {"image": bool(self.var_img.get()), "video": bool(self.var_vid.get()), "voice": bool(self.var_voice.get())}
        app.stop_event.clear()
        app.set_busy(True)
        profile = app.begin_run(self.lbl_status)
        app.save_settings()
        total = len(threads)
        self.pb.configure(maximum=max(total, 1), value=0)
        app.log(tr("Sohbet yedekle: {0} sohbet yedeklenecek → {1}", total, root_dir))

        def mark(tid, text, tag=""):
            if self.tv.exists(tid):
                self.tv.set(tid, "status", text)
                self.tv.item(tid, tags=(tag,) if tag else ())
                self.tv.see(tid)

        def work():
            ok_n = failed = files_n = msgs_n = 0
            hard = False
            try:
                for n, t in enumerate(threads, 1):
                    if app.stop_event.is_set():
                        break
                    tid, name = str(t.get("thread_id")), app.thread_title(t)
                    app.post(lambda tid=tid: mark(tid, tr("Yedekleniyor…"), "run"))
                    try:
                        res = self._export(t, root_dir, opts, profile, n, total)
                    except StopRequested:
                        app.post(lambda tid=tid: mark(tid, tr("Durduruldu")))
                        break
                    except Exception as e:
                        failed += 1
                        msg = friendly(e)
                        app.post(lambda tid=tid, msg=msg: mark(tid, tr("Hata: {0}", msg[:60]), "err"))
                        app.post(lambda name=name, msg=msg: app.log(tr("Hata ({0}): {1}", name, msg)))
                        if limit_kind(e) is not None:
                            hard = True
                            app.post(lambda: app.log(tr("Instagram sınırlama uyardı. Hesabı korumak için DURDURULDU. "
                                                     "Birkaç saat sonra tekrar dene.")))
                            break
                        continue
                    ok_n += 1
                    msgs_n += res["messages"]
                    files_n += res["files"]
                    txt = (tr("Tamam ✓  ({0} mesaj, {1} dosya, {2} indirilemedi)", res["messages"], res["files"], res["failed"])
                           if res["failed"] else tr("Tamam ✓  ({0} mesaj, {1} dosya)", res["messages"], res["files"]))
                    app.post(lambda tid=tid, txt=txt: mark(tid, txt, "done"))
                    app.post(lambda n=n: self.pb.configure(value=n))
                    app.post(lambda name=name, res=res: app.log(
                        tr("Yedeklendi: {0} → {1} mesaj, {2} dosya ({3})", name, res['messages'], res['files'], res['folder'])))
            finally:
                stopped = app.stop_event.is_set()
                app.post(lambda: self._done(ok_n, failed, msgs_n, files_n, stopped, hard, root_dir))

        app.run_bg(work)

    def _sleep(self, lo, hi):
        """Stop-aware random pause."""
        steps = max(1, int(random.uniform(lo, hi) / 0.05))
        for _ in range(steps):
            if self.app.stop_event.is_set():
                raise StopRequested()
            time.sleep(0.05)

    def _folder_for(self, root_dir, thread):
        base = safe_name(self.app.thread_title(thread))
        tid = str(thread.get("thread_id"))
        for k in range(0, 50):
            folder = os.path.join(root_dir, base if k == 0 else f"{base} ({k + 1})")
            marker = os.path.join(folder, ".thread_id")
            if not os.path.isdir(folder):
                os.makedirs(folder)
                with open(marker, "w", encoding="utf-8") as fp:
                    fp.write(tid)
                return folder
            try:
                with open(marker, encoding="utf-8") as fp:
                    if fp.read().strip() == tid:
                        return folder
            except OSError:
                with open(marker, "w", encoding="utf-8") as fp:      # adopt an untagged folder
                    fp.write(tid)
                return folder
        raise OSError(tr("klasör adı çakışması"))

    def fetch_messages(self, tid, label):
        """Whole history of one thread, oldest first."""
        app, client = self.app, self.app.client
        items, seen, users, cursor = [], set(), {}, None
        while len(items) < 300000:
            params = {"visual_message_return_type": "unseen", "direction": "older", "limit": "20"}
            if cursor:
                params["cursor"] = cursor
            resp = app.guarded(lambda p=params: client.private_request(f"direct_v2/threads/{tid}/", params=p))
            thread = resp.get("thread") or {}
            for u in thread.get("users", []):
                users[str(u.get("pk"))] = u.get("username")
            page = thread.get("items", [])
            if not page:
                break
            for it in page:
                iid = str(item_id(it) or "")
                if iid and iid not in seen:
                    seen.add(iid)
                    items.append(it)
            app.post(lambda n=len(items), label=label: self.lbl_status.configure(text=tr("{0}: {1} mesaj okundu...", label, n)))
            nxt = thread.get("oldest_cursor")
            if not (thread.get("has_older") and nxt) or nxt == cursor:
                break
            cursor = nxt
            self._sleep(1.0, 2.5)
        items.sort(key=lambda it: int(it.get("timestamp") or 0))
        return items, users

    def _export(self, thread, root_dir, opts, profile, n, total):
        app = self.app
        tid, name = str(thread.get("thread_id")), app.thread_title(thread)
        label = f"{n}/{total} · {name}"
        items, users = self.fetch_messages(tid, label)
        folder = self._folder_for(root_dir, thread)
        wanted = {k for k, v in opts.items() if v}
        lo, hi = PROFILES[profile]["download"]
        files, ok_files, failed = {}, 0, 0
        dirs = {"image": tr("gorseller"), "video": tr("videolar"), "voice": tr("sesli_mesajlar")}
        for idx, it in enumerate(items, 1):
            if app.stop_event.is_set():
                raise StopRequested()
            for kind, url in media_refs(it):
                if kind not in wanted:
                    continue
                sub = dirs[kind]
                os.makedirs(os.path.join(folder, sub), exist_ok=True)
                ts = _ts(it)
                sender = tr("ben") if self._mine(it) else safe_name(users.get(str(it.get("user_id")), "kisi"), "kisi", 30)
                fname = f"{idx:05d}_{ts:%Y%m%d-%H%M%S}_{sender}{file_ext(url, kind)}" if ts else \
                    f"{idx:05d}_{sender}{file_ext(url, kind)}"
                rel, dest = f"{sub}/{fname}", os.path.join(folder, sub, fname)
                if os.path.exists(dest) and os.path.getsize(dest) > 0:
                    files[(item_id(it), kind)] = rel
                    ok_files += 1
                    continue
                try:
                    app.guarded(lambda u=url, d=dest: fetch_to_file(u, d))      # retries drops / soft limits
                    files[(item_id(it), kind)] = rel
                    ok_files += 1
                except StopRequested:
                    raise
                except Exception as e:
                    failed += 1
                    if is_limit_error(e):
                        raise
                    app.post(lambda e=e, fname=fname: app.log(tr("Dosya indirilemedi ({0}): {1}", fname, friendly(e))))
                app.post(lambda k=ok_files + failed, label=label: self.lbl_status.configure(
                    text=tr("{0}: dosya {1} indiriliyor...", label, k)))
                self._sleep(lo, hi)
        self._write_txt(folder, thread, name, items, users, files)
        return {"messages": len(items), "files": ok_files, "failed": failed, "folder": folder}

    def _mine(self, it):
        return bool(it.get("is_sent_by_viewer")) or str(it.get("user_id")) == str(self.app.my_user_id)

    def _write_txt(self, folder, thread, name, items, users, files):
        me = self.app.my_username or "ben"
        lines = [tr("Instagram Araçları · Sohbet yedeği"),
                 tr("Sohbet     : {0}", name),
                 tr("Katılımcı  : {0}", (', '.join(sorted(set(users.values())) + [me]) if users else me)),
                 tr("Yedek tarihi: {0:%Y-%m-%d %H:%M:%S}", datetime.now()),
                 tr("Mesaj sayısı: {0}", len(items)),
                 "=" * 60, ""]
        for it in items:
            sender = tr("Ben") if self._mine(it) else (users.get(str(it.get("user_id"))) or f"ID {it.get('user_id')}")
            lines += format_message(it, sender, files)
        path = os.path.join(folder, tr("sohbet.txt"))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8-sig", newline="\r\n") as fp:      # BOM: Notepad shows Turkish letters right
            fp.write("\n".join(lines) + "\n")
        os.replace(tmp, path)

    def _done(self, ok_n, failed, msgs_n, files_n, stopped, hard, root_dir):
        app = self.app
        app.set_busy(False)
        self.last_result = {"ok": ok_n, "failed": failed, "messages": msgs_n, "files": files_n, "dir": root_dir}
        summary = tr("Yedeklenen sohbet: {0} · mesaj: {1} · dosya: {2}", ok_n, msgs_n, files_n) + (
            tr(" · hata: {0}", failed) if failed else "")
        self.lbl_status.configure(text=tr("Bitti · {0}", summary) + (tr(" · (durduruldu)") if stopped else ""))
        app.log(tr("Sohbet yedekle: bitti. {0}.", summary) + (tr(" Kullanıcı durdurdu.") if stopped else ""))
        text = tr("{0}\n\nKlasör:\n{1}", summary, root_dir)
        if hard:
            text += tr("\n\nInstagram sınırlama uyardığı için durduruldu. Birkaç saat sonra kalan sohbetleri yedekleyebilirsin.")
        ui.showinfo(app_title(), text)


# ================================================================================================ account
_MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
           "september": 9, "october": 10, "november": 11, "december": 12,
           "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
           "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}


def parse_join_date(text):
    """'September 2019' / 'Eylül 2019' / 'September 3, 2019' -> (year, month) or None."""
    if not text:
        return None
    m = re.search(r"([A-Za-zÇĞİÖŞÜçğıöşü]+)\.?\s+(?:\d{1,2},?\s+)?(\d{4})", text)
    if m and m.group(1).lower() in _MONTHS:
        return int(m.group(2)), _MONTHS[m.group(1).lower()]
    m = re.search(r"(\d{4})", text)
    return (int(m.group(1)), 1) if m else None


def account_age(join, now=None):
    """(years, months) between the join month and now."""
    now = now or datetime.now()
    months = (now.year - join[0]) * 12 + (now.month - join[1])
    return max(months, 0) // 12, max(months, 0) % 12


def mask(value, keep=2):
    """Hide the middle of an e-mail / phone so screenshots do not leak it."""
    if not value:
        return ""
    s = str(value)
    if "@" in s:
        user, _, dom = s.partition("@")
        return user[:keep] + "•" * max(len(user) - keep, 1) + "@" + dom
    return s[:keep] + "•" * max(len(s) - keep * 2, 1) + s[-keep:]


class AccountTab:
    nb_title = T("Hesap bilgisi")

    def __init__(self, app):
        self.app = app
        self.frame = ttk.Frame(app.nb, style="Page.TFrame", padding=20)
        self.loaded = False
        self.rows = {}
        self._build()
        app.nb.add(self.frame, text=tr(self.nb_title))
        self.nb_index = app.nb.index(self.frame)
        app.nb.tab(self.nb_index, state="disabled")
        self.pb = self._pb
        app.nb.bind("<<NotebookTabChanged>>", self._tab_changed, add="+")

    FIELDS = (("username", T("Kullanıcı adı")), ("full_name", T("Ad soyad")), ("pk", T("Kullanıcı ID")),
              ("created", T("Hesap açılış tarihi")), ("age", T("Hesap yaşı")), ("country", T("Ülke")),
              ("former", T("Eski kullanıcı adları")), ("posts", T("Gönderi sayısı")), ("followers", T("Takipçi")),
              ("following", T("Takip edilen")), ("kind", T("Hesap türü")), ("bio", T("Biyografi")), ("link", T("Web sitesi")),
              ("email", T("E-posta (gizli)")), ("phone", T("Telefon (gizli)")))

    def _build(self):
        f, app = self.frame, self.app
        head = ttk.Frame(f, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=tr("Hesap bilgisi"), style="H.TLabel").pack(side="left")
        self.btn_refresh = app.button(head, tr("Yenile"), self.refresh, kind="secondary")
        self.btn_refresh.pack(side="right")
        self.lbl_status = ttk.Label(f, text="", style="Sub.TLabel", wraplength=880, justify="left")
        self.lbl_status.pack(side="bottom", anchor="w", pady=(8, 0))
        self._pb = ttk.Progressbar(f, mode="determinate")
        self._pb.pack(side="bottom", fill="x", pady=(8, 0))

        card = tk.Frame(f, bg="#f9fafb")
        card.pack(fill="x", pady=(12, 0))
        top = tk.Frame(card, bg="#f9fafb")
        top.pack(fill="x", padx=18, pady=14)
        self.avatar = tk.Canvas(top, width=64, height=64, bg="#f9fafb", highlightthickness=0)
        self.avatar.create_oval(2, 2, 62, 62, fill="#facc15", outline="", tags="bg")
        self.avatar.create_text(32, 32, text="?", fill="#1f2937", font=("Segoe UI", 24, "bold"), tags="ch")
        self.avatar.pack(side="left")
        col = tk.Frame(top, bg="#f9fafb")
        col.pack(side="left", padx=16)
        self.lbl_name = tk.Label(col, text="—", bg="#f9fafb", fg="#111827", font=("Segoe UI", 16, "bold"), anchor="w")
        self.lbl_name.pack(anchor="w")
        self.lbl_handle = tk.Label(col, text="", bg="#f9fafb", fg="#6b7280", font=("Segoe UI", 11), anchor="w")
        self.lbl_handle.pack(anchor="w")

        grid = ttk.Frame(f, style="Card.TFrame")
        grid.pack(fill="both", expand=True, pady=(12, 0))
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)
        half = (len(self.FIELDS) + 1) // 2
        for i, (key, label) in enumerate(self.FIELDS):
            r, c = i % half, (i // half) * 2
            ttk.Label(grid, text=tr(label) + ":", style="Sub.TLabel").grid(row=r, column=c, sticky="ne", padx=(0, 10), pady=3)
            v = ttk.Label(grid, text="—", style="Card.TLabel", wraplength=340, justify="left")
            v.grid(row=r, column=c + 1, sticky="nw", pady=3, padx=(0, 24))
            self.rows[key] = v
        ttk.Label(f, style="Sub.TLabel", wraplength=880, justify="left",
                  text=tr("Hesap açılış tarihi Instagram'ın 'Bu hesap hakkında' bilgisinden okunur; Instagram bunu "
                       "bazı hesaplarda vermeyebilir. E-posta ve telefon ekranda kısmen gizlenir.")
                  ).pack(side="bottom", anchor="w")

    # ---- integration -----------------------------------------------------------------------------
    def enable(self, on):
        self.app.nb.tab(self.nb_index, state="normal" if on else "disabled")

    def on_busy(self, busy):
        self.btn_refresh.configure(state="disabled" if busy else "normal")

    def reset(self):
        self.loaded = False
        for v in self.rows.values():
            v.configure(text="—")
        self.lbl_name.configure(text="—")
        self.lbl_handle.configure(text="")
        self.avatar.itemconfigure("ch", text="?")
        self.lbl_status.configure(text="")

    def load_protected(self):
        self.loaded = False

    def render(self):
        pass

    def _tab_changed(self, _event):
        try:
            current = self.app.nb.index(self.app.nb.select())
        except tk.TclError:
            return
        if current == self.nb_index and not self.loaded and self.app.client is not None and not self.app.busy:
            self.refresh()

    # ---- data ------------------------------------------------------------------------------------
    def refresh(self):
        app = self.app
        if app.busy or app.client is None:
            return
        app.stop_event.clear()
        app.set_busy(True)
        self._pb.configure(mode="indeterminate")
        self._pb.start(12)
        self.lbl_status.configure(text=tr("Hesap bilgileri okunuyor..."))
        app.begin_run(self.lbl_status)
        uid = app.my_user_id

        def work():
            data, notes = {}, []
            c = app.client
            try:
                acc = app.guarded(lambda: c.account_info())
                data.update(username=acc.username, full_name=acc.full_name, pk=str(acc.pk), bio=acc.biography or "",
                            link=acc.external_url or "", email=mask(acc.email), phone=mask(acc.phone_number),
                            private=bool(acc.is_private), verified=bool(acc.is_verified), business=bool(acc.is_business))
            except StopRequested:
                raise
            except Exception as e:
                notes.append(tr("Hesap bilgisi okunamadı: {0}", friendly(e)))
            try:
                usr = app.guarded(lambda: c.user_info(uid))
                data.update(posts=usr.media_count, followers=usr.follower_count, following=usr.following_count)
                data.setdefault("username", usr.username)
                data.setdefault("full_name", usr.full_name)
            except StopRequested:
                raise
            except Exception as e:
                notes.append(tr("Profil sayıları okunamadı: {0}", friendly(e)))
            try:
                about = app.guarded(lambda: c.user_about_v1(uid))
                data.update(created=(about.date or "").strip(), country=(about.country or "").strip(),
                            former=(about.former_usernames or "").strip())
            except StopRequested:
                raise
            except Exception as e:
                notes.append(tr("Hesap açılış tarihi Instagram'dan alınamadı "
                             "(Ayarlar → Hesap merkezi → Bilgilerini indir bölümünde bulunur)."))
            app.post(lambda: self._show(data, notes))

        def guarded_work():
            try:
                work()
            except StopRequested:
                app.post(lambda: self._show({}, [tr("Durduruldu.")]))

        app.run_bg(guarded_work)

    def _show(self, data, notes):
        self._pb.stop()
        self._pb.configure(mode="determinate", value=0)
        self.app.set_busy(False)
        self.loaded = bool(data)
        fmt = lambda v: (f"{v:,}".replace(",", ".") if get_language() == "tr" else f"{v:,}") if isinstance(v, int) else (v or "—")
        self.lbl_name.configure(text=data.get("full_name") or data.get("username") or "—")
        self.lbl_handle.configure(text=f"@{data['username']}" if data.get("username") else "")
        self.avatar.itemconfigure("ch", text=(data.get("username") or "?")[:1].upper())
        kinds = []
        if data.get("private") is not None and "private" in data:
            kinds.append(tr("Gizli hesap") if data["private"] else tr("Herkese açık hesap"))
        if data.get("verified"):
            kinds.append(tr("Doğrulanmış ✓"))
        if data.get("business"):
            kinds.append(tr("İşletme hesabı"))
        created = data.get("created", "")
        join = parse_join_date(created)
        age = ""
        if join:
            y, m = account_age(join)
            age = ((tr("{0} yıl ", y) if y else "") + tr("{0} ay", m)) if (y or m) else tr("1 aydan az")
        values = {"username": data.get("username"), "full_name": data.get("full_name"), "pk": data.get("pk"),
                  "created": created or None, "age": age or None, "country": data.get("country"),
                  "former": data.get("former"), "posts": fmt(data.get("posts")) if "posts" in data else None,
                  "followers": fmt(data.get("followers")) if "followers" in data else None,
                  "following": fmt(data.get("following")) if "following" in data else None,
                  "kind": " · ".join(kinds) or None, "bio": data.get("bio"), "link": data.get("link"),
                  "email": data.get("email"), "phone": data.get("phone")}
        for key, lbl in self.rows.items():
            lbl.configure(text=values.get(key) or "—")
        self.lbl_status.configure(text=" ".join(notes) if notes else tr("Bilgiler güncel."))
        self.app.log(tr("Hesap bilgisi güncellendi.") + (tr(" ({0} uyarı)", len(notes)) if notes else ""))
