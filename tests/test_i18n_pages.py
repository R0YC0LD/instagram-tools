"""English mode end to end: chat backup (file/folder names), saved posts, account page, auto DM cleanup."""
import os, sys, re, time, types, tempfile, json
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
from datetime import datetime
import tkinter as tk
import igdm_app as g
import igdm_extra as X
import igdm_i18n as I

D = tempfile.mkdtemp(); BK = os.path.join(D, "backups")
g.SETTINGS_FILE = os.path.join(D, "s.json"); g.PROTECTED_FILE = os.path.join(D, "p.json"); g.LOG_FILE = os.path.join(D, "l.log"); g.KEEP_FILE = os.path.join(D, "k.json")
for p in g.PROFILES.values(): p.update(unsend=(0, 0), hide=(0, 0), story=(0, 0), unblock=(0, 0), unlike=(0, 0), unsave=(0, 0), download=(0, 0), rest=(0, 0), batch=10**6)
g.SOFT_PAUSE = (0, 0); g.NET_BACKOFF = (0, 0, 0, 0)
real_sleep = time.sleep; g.time.sleep = lambda s: real_sleep(0.0005)
n_ok = 0
def check(name, cond, detail=""):
    global n_ok
    assert cond, "FAIL: " + name + (f"  -> {detail}" if detail else "")
    n_ok += 1; print("PASS", name)

def ts(m): return int((datetime(2026, 3, 1, 12, 0, 0).timestamp() + m * 60) * 1_000_000)
def msgs(tid, other):
    return [
        {"item_id": f"{tid}-1", "user_id": other, "item_type": "text", "text": "Hi there", "timestamp": ts(1)},
        {"item_id": f"{tid}-2", "user_id": 7, "item_type": "text", "text": "Hello", "timestamp": ts(2)},
        {"item_id": f"{tid}-3", "user_id": other, "item_type": "media", "timestamp": ts(3), "media": {"image_versions2": {"candidates": [{"url": f"https://scontent.cdninstagram.com/{tid}/one.jpg"}]}}},
        {"item_id": f"{tid}-4", "user_id": other, "item_type": "voice_media", "timestamp": ts(4), "voice_media": {"media": {"audio": {"audio_src": f"https://scontent.cdninstagram.com/{tid}/v.m4a"}}}},
        {"item_id": f"{tid}-5", "user_id": 7, "item_type": "like", "timestamp": ts(5)},
    ]
THREADS = [{"thread_id": str(100 * (i + 1)), "thread_title": "", "users": [{"pk": 10 + i, "username": f"friend{i}"}],
            "last_activity_at": ts(100 - i), "items": [{"item_id": f"l{i}", "user_id": 10 + i, "item_type": "text", "text": "last", "timestamp": ts(100 - i)}]} for i in range(6)]
OTHER = {t["thread_id"]: t["users"][0]["pk"] for t in THREADS}
SAVED = [{"media": {"id": f"{6000 + i}_9", "media_type": 1, "taken_at": 1700000000 + i, "user": {"username": f"u{i}"}, "caption": {"text": f"c{i}"}}} for i in range(5)]
unsaved, hidden = [], []

class FakeClient:
    uuid = "u"; token = "t"; user_id = "7"
    def __init__(self): self.challenge_code_handler = self.change_password_handler = None
    def login_by_sessionid(self, sid): pass
    def account_info(self): return types.SimpleNamespace(pk="7", username="onur.test", full_name="Onur Test", is_private=True, is_verified=False, biography="hello", external_url="", is_business=True, email="onur.test@example.com", phone_number="+905551234567", birthday=None, gender=None)
    def user_info(self, uid): return types.SimpleNamespace(username="onur.test", full_name="Onur Test", media_count=1234, follower_count=56789, following_count=321)
    def user_about_v1(self, uid): return types.SimpleNamespace(date="September 2019", country="Turkey", former_usernames="")
    def media_unsave(self, mid): unsaved.append(str(mid)); return True
    def direct_thread_hide(self, tid): hidden.append(str(tid)); return True
    def private_request(self, ep, params=None, data=None, with_signature=True):
        params = params or {}
        if ep == "direct_v2/inbox/": return {"inbox": {"threads": THREADS, "has_older": False}}
        if ep.startswith("direct_v2/threads/") and ep.endswith("hide/"): hidden.append(ep.split("/")[2]); return {"status": "ok"}
        if ep.startswith("direct_v2/threads/") and ep.endswith("/"):
            tid = ep.split("/")[2]; allm = sorted(msgs(tid, OTHER[tid]), key=lambda m: -int(m["timestamp"]))
            th = next(t for t in THREADS if t["thread_id"] == tid)
            return {"thread": {"users": th["users"], "items": allm, "has_older": False, "oldest_cursor": ""}}
        if ep == "feed/saved/posts/": return {"items": SAVED, "next_max_id": ""}
        raise AssertionError(ep)
g.Client = FakeClient; g.load_session = lambda *a, **k: False
infos = []; asked = []
g.ui.showinfo = lambda *a, **k: infos.append(a[1] if len(a) > 1 else "")
g.ui.showwarning = lambda *a, **k: infos.append("WARN " + str(a[1:]))
g.ui.askstring = lambda title, prompt, **k: (asked.append(str(prompt)), "DELETE" if "DELETE" in str(prompt) else "REMOVE")[1]
g.ui.askyesno = lambda *a, **k: True
X.fetch_to_file = lambda url, path, timeout=None: open(path, "wb").write(b"BIN:" + url.encode())

I.set_language("en")
root = tk.Tk(); app = g.App(root)
def pump(cond=lambda: True, t=30):
    end = time.time() + t
    while time.time() < end:
        root.update()
        if cond(): return True
        real_sleep(0.005)
    return cond()
app.var_sid.set("1234567890:" + "A" * 40); app.do_login_session(); pump(lambda: app.client is not None); pump(lambda: not app.busy)
saved_tab, backup, account = app.bulk_tabs[3], app.bulk_tabs[4], app.bulk_tabs[5]
check("window title is English", root.title().startswith("PACMANGRAM v"))

# ---- saved posts
saved_tab.scan(); pump(lambda: not app.busy and len(saved_tab.items) == 5)
saved_tab.start(); infos.clear(); pump(lambda: not app.busy and infos)
check("saved: 5 posts unsaved after typing REMOVE", len(unsaved) == 5 and asked and "REMOVE" in asked[-1], (unsaved, asked[-1:]))

# ---- backup
backup.var_dir.set(BK); backup.var_img.set(True); backup.var_vid.set(False); backup.var_voice.set(True)
backup.load_chats(); check("backup: chats listed", pump(lambda: not app.busy and len(backup.threads) == 6))
backup.tv.selection_set(["100", "200"]); infos.clear(); backup.start(); check("backup finished", pump(lambda: not app.busy and infos, 60))
check("backup: one folder per person", sorted(os.listdir(BK)) == ["friend0", "friend1"], os.listdir(BK))
f0 = os.path.join(BK, "friend0")
check("backup: English file and sub-folder names (chat.txt, images, voice_messages)", os.path.exists(os.path.join(f0, "chat.txt")) and os.path.isdir(os.path.join(f0, "images")) and os.path.isdir(os.path.join(f0, "voice_messages")), os.listdir(f0))
txt = open(os.path.join(f0, "chat.txt"), encoding="utf-8-sig").read()
check("backup: chat.txt header is English", "PACMANGRAM · Chat backup" in txt and "Messages    : 5" in txt and "Participants: friend0" in txt, txt[:300])
check("backup: chat.txt lines use English labels", "[Like]" in txt and "Hi there" in txt and "me:" in txt.lower(), txt)
check("backup: status row says Done", "Done" in backup.tv.set("100", "status"), backup.tv.set("100", "status"))
check("backup: summary dialog is English", any("Backed-up chats" in i or "Backed up" in i or "finished" in i.lower() for i in infos), infos)

# ---- account page
app.nb.select(9); check("account page loads", pump(lambda: account.loaded and not app.busy))
v = {k: lbl.cget("text") for k, lbl in account.rows.items()}
check("account: English values", v["kind"] == "Private account · Business account" and v["posts"] == "1,234" and v["followers"] == "56,789", v)
check("account: age is English", re.fullmatch(r"\d+ yr \d+ mo|\d+ yr |\d+ mo", v["age"]) is not None, v["age"])

# ---- auto DM cleanup
app.auto_scan(); pump(lambda: not app.busy and app.auto_threads)
app.var_keep.set(2); app.var_keep_pins.set(False); app.auto_render()
check("auto cleanup: plan keeps 2, deletes 4", len(app.auto_todo) == 4 and len(app.auto_threads) == 6)
check("auto cleanup: status column is English", {app.tv_auto.set(i, "status") for i in app.tv_auto.get_children()} == {"Keep", "Delete"}, {app.tv_auto.set(i, "status") for i in app.tv_auto.get_children()})
asked.clear(); infos.clear(); app.auto_start(); pump(lambda: not app.busy and infos)
check("auto cleanup: English confirm word DELETE asked and accepted", asked and "DELETE" in asked[0] and len(hidden) == 4, (asked[:1], hidden))
check("auto cleanup: confirm text has no Turkish left", not re.search(r"[ğışĞİ]", asked[0]), asked[0][:200])

check("nothing fell back to Turkish", not I.missing(), sorted(I.missing())[:6])
root.destroy()
print(f"\n{n_ok} checks passed")
