"""
make_screenshots.py  -  renders the README images from the real UI, using a FAKE Instagram client.
No account, no network, no personal data: everything you see in docs/ is sample data.

Windows only (uses PrintWindow, so it works even if the window is covered). Needs Pillow:  pip install pillow
Output: docs/screenshots/*.png, docs/intro.gif
"""

import ctypes
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

import tkinter as tk  # noqa: E402
from PIL import Image  # noqa: E402

import igdm_app as g  # noqa: E402
import igdm_intro  # noqa: E402
import igdm_ui as ui  # noqa: E402

SHOTS = os.path.join(ROOT, "docs", "screenshots")
os.makedirs(SHOTS, exist_ok=True)
tmp = tempfile.mkdtemp()                                   # never touch the real settings / logs
g.SETTINGS_FILE, g.PROTECTED_FILE = os.path.join(tmp, "s.json"), os.path.join(tmp, "p.json")
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
NAMES = ["ayse.yilmaz", "mehmet_k", "Hafta sonu grubu", "zeynep", "can.demir", "elif_s", "burak", "selin.a",
         "old_friend", "spam_account"]
THREADS = []
for i, n in enumerate(NAMES, 1):
    THREADS.append({"thread_id": str(i), "thread_title": n, "users": [{"pk": 100 + i, "username": n}], "is_pin": i == 2,
                    "last_activity_at": int((NOW - timedelta(days=i * 9)).timestamp() * 1e6),
                    "items": [{"text": ["Görüşürüz o zaman!", "tamam olur", "Foto attım bak", "Akşam müsait misin?"][i % 4],
                               "item_type": "text"}]})
TEXTS = ["Selam nasılsın?", "İyiyim sen?", "Ben de iyiyim, akşam çıkalım mı?", "Olur, saat kaçta?", "8 gibi uygun mu",
         "Tamam görüşürüz", "Geç kalma :)", "Yoldayım", "Geldim", "Neredesin?", "Buradayım", "Peki"]
MSGS = [{"item_id": str(i), "user_id": 7 if i % 3 else 101, "text": t, "item_type": "text",
         "timestamp": int((NOW - timedelta(hours=i * 5)).timestamp() * 1e6)} for i, t in enumerate(TEXTS, 1)]
DAYS = [types.SimpleNamespace(id=f"d{i}", timestamp=NOW - timedelta(days=37 * i), media_count=2 + i % 4)
        for i in range(1, 15)]
BLOCKED = [{"user_id": 900 + i, "username": f"engelli_{i}", "full_name": f"Kişi {i}",
            "block_at": int((NOW - timedelta(days=11 * i)).timestamp())} for i in range(1, 19)]
LIKED = [{"id": f"{7000 + i}_9", "media_type": [1, 2, 8][i % 3], "taken_at": int((NOW - timedelta(days=5 * i)).timestamp()),
          "user": {"username": f"hesap_{i}"}, "caption": {"text": f"Örnek gönderi açıklaması numara {i} #instagram"}}
         for i in range(1, 25)]


class FakeClient:
    uuid, token, user_id = "u", "t", "7"

    def __init__(self):
        self.challenge_code_handler = self.change_password_handler = None

    def login_by_sessionid(self, sid): pass
    def account_info(self): return types.SimpleNamespace(username="pacman.demo", pk=7)
    def with_default_data(self, d): return d
    def media_id(self, pk): return f"{pk}_7"
    def _archive_story_reels(self, r): return list(r["reels"].values())

    def archive_story_days_paginated_v1(self, amount=0, end_cursor="", include_memories=True, reel_id=""):
        return DAYS, ""

    def private_request(self, ep, params=None, data=None, with_signature=True):
        if ep == "direct_v2/inbox/":
            return {"inbox": {"threads": THREADS, "has_older": False}}
        if ep.startswith("direct_v2/threads/") and ep.endswith("/"):
            return {"thread": {"users": [{"pk": 101, "username": "ayse.yilmaz"}], "items": MSGS, "has_older": False}}
        if ep == "users/blocked_list/":
            return {"blocked_list": BLOCKED, "next_max_id": ""}
        if ep == "feed/liked/":
            return {"items": LIKED, "next_max_id": ""}
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


def main():
    root = tk.Tk()
    app = g.App(root)
    root.geometry("1340x860+40+40")

    def shot(name):
        pump(root, t=0.6)
        capture(root).save(os.path.join(SHOTS, name))
        print("saved", name)

    app.log("Program açıldı. Ağ kilidi aktif: yalnızca Instagram/Facebook sunucularına bağlanılır.")
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
    app.log("Instagram yavaşlama uyarısı verdi (1/2). 6 dk dinlenilecek, sonra daha yavaş devam edilecek.")
    shot("04-dm-cleanup.png")

    app.nb.select(4)
    tab = app.bulk_tabs[0]
    tab.var_date.set((NOW - timedelta(days=100)).strftime("%d.%m.%Y"))
    tab.scan()
    pump(root, lambda: not app.busy and tab.items)
    shot("05-stories.png")

    app.nb.select(5)
    tab = app.bulk_tabs[1]
    tab.scan()
    pump(root, lambda: not app.busy and tab.items)
    tab.toggle_protect("903")
    tab.tv.selection_set(())
    shot("06-blocked.png")

    app.nb.select(6)
    tab = app.bulk_tabs[2]
    tab.scan()
    pump(root, lambda: not app.busy and tab.items)
    shot("07-likes.png")

    def grab_dialog():
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel):
                capture(w).save(os.path.join(SHOTS, "08-confirm-dialog.png"))
                print("saved 08-confirm-dialog.png")
                w.destroy()
                return

    root.after(700, grab_dialog)
    ui.askstring("Onay gerekli", "12 sohbet komple silinecek, 4 sohbet korunacak.\nTahmini süre (yalnızca silme): "
                 "yaklaşık 8 dk (Dengeli hız).\n\nBu işlem geri alınamaz. Silinen sohbetler gelen kutundan kalkar.\n\n"
                 "Onaylamak için  SİL  yaz:", parent=root)
    root.destroy()

    # ---- intro: still + animated GIF (real speed, ~8 fps)
    root = tk.Tk()
    root.geometry("1100x760+40+40")
    root.title("Instagram DM Temizleyici")
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
    still = frames[len(frames) * 3 // 10]
    still.save(os.path.join(SHOTS, "09-intro.png"))
    small = [f.resize((560, int(f.height * 560 / f.width)), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=48)
             for f in frames]
    gif = os.path.join(ROOT, "docs", "intro.gif")
    small[0].save(gif, save_all=True, append_images=small[1:], duration=140, loop=0, optimize=True, disposal=1)
    print(f"saved intro.gif ({len(small)} frames, {os.path.getsize(gif) / 1e6:.1f} MB)")

    Image.open(os.path.join(ROOT, "assets", "app_preview.png")).resize((256, 256), Image.LANCZOS).save(
        os.path.join(ROOT, "docs", "icon.png"))


if __name__ == "__main__":
    main()
