"""
make_screenshots.py  -  renders the README images from the real UI, using a FAKE Instagram client.
No account, no network, no personal data: everything you see in docs/ is sample data.

Windows only (uses PrintWindow, so it works even if the window is covered). Needs Pillow:  pip install pillow
Output: docs/screenshots/<lang>/*.png and docs/intro-<lang>.gif   (lang = en, tr)
"""

import ctypes
import json
import os
import sys
import tempfile
import time
import types
from ctypes import wintypes as wt
from datetime import datetime, timedelta

ctypes.windll.shcore.SetProcessDpiAwareness(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import tkinter as tk  # noqa: E402
from PIL import Image  # noqa: E402

import igdm_app as g  # noqa: E402
import igdm_extra as X  # noqa: E402
import igdm_i18n as I  # noqa: E402
import igdm_intro  # noqa: E402
import igdm_ui as ui  # noqa: E402
from i18n_keys import collect  # noqa: E402

tmp = tempfile.mkdtemp()                                   # never touch the real settings / logs
g.PROTECTED_FILE = os.path.join(tmp, "p.json")
g.LOG_FILE, g.KEEP_FILE = os.path.join(tmp, "l.log"), os.path.join(tmp, "k.json")


def capture(win):
    """Render a window through PrintWindow and return it as a PIL image."""
    win.update_idletasks()
    win.update()
    hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
    r = wt.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = ctypes.windll.user32.GetWindowDC(hwnd)
    mdc = ctypes.windll.gdi32.CreateCompatibleDC(hdc)
    bmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc, w, h)
    ctypes.windll.gdi32.SelectObject(mdc, bmp)
    ctypes.windll.user32.PrintWindow(hwnd, mdc, 2)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("x", wt.LONG), ("y", wt.LONG), ("c", wt.DWORD), ("i", wt.DWORD)]

    bi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    ctypes.windll.gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    ctypes.windll.gdi32.DeleteObject(bmp)
    ctypes.windll.gdi32.DeleteDC(mdc)
    ctypes.windll.user32.ReleaseDC(hwnd, hdc)
    return img


# ------------------------------------------------------------------------------------- sample data
NOW = datetime.now()
SAMPLE = {
    "tr": {
        "names": ["ayse.yilmaz", "mehmet_k", "Hafta sonu grubu", "zeynep", "can.demir", "elif_s", "burak", "selin.a",
                  "old_friend", "spam_account"],
        "last": ["Görüşürüz o zaman!", "tamam olur", "Foto attım bak", "Akşam müsait misin?"],
        "texts": ["Selam nasılsın?", "İyiyim sen?", "Ben de iyiyim, akşam çıkalım mı?", "Olur, saat kaçta?",
                  "8 gibi uygun mu", "Tamam görüşürüz", "Geç kalma :)", "Yoldayım", "Geldim", "Neredesin?",
                  "Buradayım", "Peki"],
        "blocked": "Kişi", "blk": "engelli", "caption": "Örnek gönderi açıklaması numara {0} #instagram",
        "acct": "hesap", "bio": "Pacman'in Instagram'ı", "backup_dir": r"C:\Users\Demo\Belgeler\Instagram Yedekleri",
    },
    "en": {
        "names": ["alice.smith", "mike_k", "Weekend group", "emma", "john.doe", "lily_s", "ben", "sophie.a",
                  "old_friend", "spam_account"],
        "last": ["See you then!", "sounds good", "Sent you a photo", "Are you free tonight?"],
        "texts": ["Hey, how are you?", "Good, you?", "Same here, want to go out tonight?", "Sure, what time?",
                  "Around 8?", "Okay, see you", "Don't be late :)", "On my way", "I'm here", "Where are you?",
                  "Right here", "Fine"],
        "blocked": "Person", "blk": "blocked", "caption": "Sample post caption number {0} #instagram",
        "acct": "account", "bio": "Pacman's Instagram", "backup_dir": r"C:\Users\Demo\Documents\Instagram Backups",
    },
}
S = SAMPLE["tr"]
THREADS = MSGS = DAYS = BLOCKED = LIKED = []


def build_data(lang):
    global S, THREADS, MSGS, DAYS, BLOCKED, LIKED
    S = SAMPLE[lang]
    THREADS = [{"thread_id": str(i), "thread_title": n, "users": [{"pk": 100 + i, "username": n}], "is_pin": i == 2,
                "last_activity_at": int((NOW - timedelta(days=i * 9)).timestamp() * 1e6),
                "items": [{"text": S["last"][i % 4], "item_type": "text"}]} for i, n in enumerate(S["names"], 1)]
    MSGS = [{"item_id": str(i), "user_id": 7 if i % 3 else 101, "text": t, "item_type": "text",
             "timestamp": int((NOW - timedelta(hours=i * 5)).timestamp() * 1e6)} for i, t in enumerate(S["texts"], 1)]
    DAYS = [types.SimpleNamespace(id=f"d{i}", timestamp=NOW - timedelta(days=37 * i), media_count=2 + i % 4)
            for i in range(1, 15)]
    BLOCKED = [{"user_id": 900 + i, "username": f"{S['blk']}_{i}", "full_name": f"{S['blocked']} {i}",
                "block_at": int((NOW - timedelta(days=11 * i)).timestamp())} for i in range(1, 19)]
    LIKED = [{"id": f"{7000 + i}_9", "media_type": [1, 2, 8][i % 3], "taken_at": int((NOW - timedelta(days=5 * i)).timestamp()),
              "user": {"username": f"{S['acct']}_{i}"}, "caption": {"text": S["caption"].format(i)}}
             for i in range(1, 25)]


class FakeClient:
    uuid, token, user_id = "u", "t", "7"

    def __init__(self):
        self.challenge_code_handler = self.change_password_handler = None

    def login_by_sessionid(self, sid): pass
    def account_info(self):
        return types.SimpleNamespace(pk="7", username="pacman.demo", full_name="Pacman Demo", is_private=False,
                                     is_verified=False, biography=S["bio"], external_url="https://example.com/pacman",
                                     is_business=False, email="pacman.demo@example.com", phone_number="+905551234567",
                                     birthday=None, gender=None)
    def user_info(self, uid):
        return types.SimpleNamespace(username="pacman.demo", full_name="Pacman Demo", media_count=248,
                                     follower_count=12840, following_count=311)
    def user_about_v1(self, uid):
        return types.SimpleNamespace(date="March 2018", country="Türkiye" if S is SAMPLE["tr"] else "Turkey", former_usernames="pacman_old")
    def with_default_data(self, d): return d
    def media_id(self, pk): return f"{pk}_7"
    def _archive_story_reels(self, r): return list(r["reels"].values())

    def archive_story_days_paginated_v1(self, amount=0, end_cursor="", include_memories=True, reel_id=""):
        return DAYS, ""

    def private_request(self, ep, params=None, data=None, with_signature=True):
        if ep == "direct_v2/inbox/":
            return {"inbox": {"threads": THREADS, "has_older": False}}
        if ep.startswith("direct_v2/threads/") and ep.endswith("/"):
            return {"thread": {"users": [{"pk": 101, "username": S["names"][0]}], "items": MSGS, "has_older": False}}
        if ep == "users/blocked_list/":
            return {"blocked_list": BLOCKED, "next_max_id": ""}
        if ep in ("feed/liked/", "feed/saved/posts/"):
            return {"items": LIKED if ep == "feed/liked/" else [{"media": m} for m in LIKED[::-1]], "next_max_id": ""}
        raise AssertionError(ep)


g.Client = FakeClient
g.load_session = lambda *a, **k: False


def pump(root, cond=lambda: True, t=20.0):
    end = time.time() + t
    while time.time() < end:
        root.update()
        if cond():
            return
        time.sleep(0.01)


def confirm_key():
    return next(k for k, _ in collect() if k.startswith("{0} sohbet komple silinecek"))


def run_language(lang):
    out = os.path.join(ROOT, "docs", "screenshots", lang)
    os.makedirs(out, exist_ok=True)
    build_data(lang)
    I.set_language(lang)
    g.SETTINGS_FILE = os.path.join(tmp, f"s_{lang}.json")
    with open(g.SETTINGS_FILE, "w", encoding="utf-8") as fp:
        json.dump({"language": lang}, fp)
    tr = I.tr

    root = tk.Tk()
    app = g.App(root)
    root.geometry("1340x860+40+40")

    def shot(name):
        pump(root, t=0.6)
        capture(root).save(os.path.join(out, name))
        print("saved", lang, name)

    shot("01-login.png")
    app.var_sid.set("1234567890:" + "A" * 40)
    app.do_login_session()
    pump(root, lambda: app.client is not None)
    pump(root, lambda: len(app.tv_threads.get_children()) == 10)
    shot("02-chats.png")

    app.tv_threads.selection_set("1")
    app.choose_thread()
    pump(root, lambda: not app.busy and len(app.tv_msgs.get_children()) == 12)
    shot("03-messages.png")

    app.nb.select(3)
    app.auto_scan()
    pump(root, lambda: not app.busy and app.auto_threads)
    app.var_keep.set(4)
    app.toggle_protect("8")
    app.tv_auto.selection_set(())          # show the green "protected" row un-selected
    app.log(tr("Instagram yavaşlama uyarısı verdi ({0}/{1}). {2} dinlenilecek, sonra daha yavaş devam edilecek.", 1, 2, tr("{0:.0f} dk", 6)))
    shot("04-dm-cleanup.png")

    def bulk(page, idx, name, protect=None, before=None):
        app.nb.select(page)
        tab = app.bulk_tabs[idx]
        if before:
            before(tab)
        tab.scan()
        pump(root, lambda: not app.busy and tab.items)
        if protect:
            tab.toggle_protect(protect)
        tab.tv.selection_set(())
        shot(name)
        return tab

    bulk(4, 0, "05-stories.png", before=lambda t: t.var_date.set((NOW - timedelta(days=100)).strftime("%d.%m.%Y")))
    bulk(5, 1, "06-blocked.png", protect="903")
    bulk(6, 2, "07-likes.png", protect="7003_9")
    bulk(7, 3, "08-saved.png", protect="7020_9")

    app.nb.select(8)
    backup = app.bulk_tabs[4]
    backup.var_dir.set(S["backup_dir"])
    backup.load_chats()
    pump(root, lambda: not app.busy and len(backup.threads) == 10)
    backup.tv.selection_set([str(i) for i in range(1, 5)])
    shot("09-backup.png")

    app.nb.select(9)
    pump(root, lambda: app.bulk_tabs[5].loaded and not app.busy)
    shot("10-account.png")

    def grab_dialog():
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel):
                capture(w).save(os.path.join(out, "11-confirm-dialog.png"))
                print("saved", lang, "11-confirm-dialog.png")
                w.destroy()
                return

    root.after(700, grab_dialog)
    ui.askstring(tr("Onay gerekli"), tr(confirm_key(), 12, 4, tr("{0:.0f} dk", 8), tr("Dengeli"), "", tr("SİL")), parent=root)
    root.destroy()

    # ---- intro: still + animated GIF (real speed, ~8 fps)
    root = tk.Tk()
    root.geometry("1100x760+40+40")
    root.title(I.app_title())
    ui.set_window_icon(root)
    intro = igdm_intro.Intro(root)
    frames, t0, next_at = [], time.time(), 0.0
    while not intro.done and time.time() - t0 < 40:
        root.update()
        el = time.time() - t0
        if el >= next_at:
            frames.append(capture(root))
            next_at = el + 0.14
        time.sleep(0.004)
    root.destroy()
    frames[len(frames) * 3 // 10].save(os.path.join(out, "12-intro.png"))
    small = [f.resize((560, int(f.height * 560 / f.width)), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=48)
             for f in frames]
    gif = os.path.join(ROOT, "docs", f"intro-{lang}.gif")
    small[0].save(gif, save_all=True, append_images=small[1:], duration=140, loop=0, optimize=True, disposal=1)
    print(f"saved intro-{lang}.gif ({len(small)} frames, {os.path.getsize(gif) / 1e6:.1f} MB)")


def main():
    for lang in ("en", "tr"):
        run_language(lang)
    Image.open(os.path.join(ROOT, "assets", "app_preview.png")).resize((256, 256), Image.LANCZOS).save(
        os.path.join(ROOT, "docs", "icon.png"))


if __name__ == "__main__":
    main()
