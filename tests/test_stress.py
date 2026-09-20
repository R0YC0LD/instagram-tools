"""Stress test: a long autonomous run (400 likes + 60 blocked accounts) with random connection drops and
Instagram 'please wait' warnings. Every item must still be processed exactly once and the UI must end unlocked."""
import os, sys, time, types, random, tempfile
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import tkinter as tk
import igdm_app as g
from instagrapi.exceptions import PleaseWaitFewMinutes

D = tempfile.mkdtemp()
g.SETTINGS_FILE = os.path.join(D, "s.json"); g.PROTECTED_FILE = os.path.join(D, "p.json"); g.LOG_FILE = os.path.join(D, "l.log"); g.KEEP_FILE = os.path.join(D, "k.json")
for p in g.PROFILES.values(): p.update(unsend=(0, 0), hide=(0, 0), story=(0, 0), unblock=(0, 0), unlike=(0, 0), rest=(0, 0), batch=25)
g.SOFT_PAUSE = (0, 0); g.LONG_REST = (0, 0); g.NET_BACKOFF = (0, 0, 0, 0)
real_sleep = time.sleep; g.time.sleep = lambda s: real_sleep(0.0005)
rng = random.Random(42)
LIKED = [{"id": f"{9000 + i}_9", "media_type": 1, "taken_at": 1700000000 + i, "user": {"username": f"u{i}"}, "caption": None} for i in range(400)]
BLOCKED = [{"user_id": 500 + i, "username": f"b{i}", "full_name": "", "block_at": 1700000000 + i} for i in range(60)]
done_likes, done_unblocks = [], []

def noise():
    r = rng.random()
    if r < 0.05: raise ConnectionError("Wi-Fi dropped")
    if r < 0.07: raise PleaseWaitFewMinutes("Please wait a few minutes")

class FakeClient:
    uuid = "u"; token = "t"; user_id = "7"
    def __init__(self): self.challenge_code_handler = self.change_password_handler = None
    def login_by_sessionid(self, sid): pass
    def account_info(self): return types.SimpleNamespace(username="stress", pk=7)
    def media_unlike(self, mid): noise(); done_likes.append(mid); return True
    def user_unblock(self, uid): noise(); done_unblocks.append(uid); return True
    def private_request(self, ep, params=None, data=None, with_signature=True):
        if ep == "direct_v2/inbox/": return {"inbox": {"threads": [], "has_older": False}}
        s = int((params or {}).get("max_id") or 0)
        if ep == "feed/liked/": return {"items": LIKED[s:s + 40], "next_max_id": str(s + 40) if s + 40 < len(LIKED) else ""}
        if ep == "users/blocked_list/": return {"blocked_list": BLOCKED[s:s + 20], "next_max_id": str(s + 20) if s + 20 < len(BLOCKED) else ""}
        raise AssertionError(ep)
g.Client = FakeClient; g.load_session = lambda *a, **k: False
infos = []; g.ui.showinfo = lambda *a, **k: infos.append(a[1] if len(a) > 1 else ""); g.ui.askstring = lambda *a, **k: "KALDIR"

root = tk.Tk(); app = g.App(root)
def pump(cond, t=120):
    end = time.time() + t
    while time.time() < end:
        root.update()
        if cond(): return True
        real_sleep(0.002)
    return False
n = 0
def check(name, cond):
    global n
    assert cond, "FAIL: " + name
    n += 1; print("PASS", name)

app.var_sid.set("1234567890:" + "A" * 40); app.do_login_session(); pump(lambda: app.client is not None); pump(lambda: not app.busy)
app.var_autoresume.set(True)
likes, blocked = app.bulk_tabs[2], app.bulk_tabs[1]
likes.scan(); check("400 likes scanned despite random errors", pump(lambda: not app.busy and len(likes.items) == 400))
t0 = time.time(); likes.start(); check("likes run finished", pump(lambda: not app.busy and infos))
check("every like removed exactly once (no loss, no duplicates)", sorted(done_likes) == sorted(x["id"] for x in LIKED) and len(done_likes) == 400)
check("UI unlocked and list empty afterwards", not app.busy and likes.items == [] and int(likes.pb.cget("value")) == int(likes.pb.cget("maximum")))
infos.clear()
blocked.scan(); check("60 blocked scanned", pump(lambda: not app.busy and len(blocked.items) == 60))
blocked.start(); check("unblock run finished", pump(lambda: not app.busy and infos))
check("every account unblocked exactly once", sorted(done_unblocks) == sorted(str(b["user_id"]) for b in BLOCKED) or sorted(map(str, done_unblocks)) == sorted(str(b["user_id"]) for b in BLOCKED))
log = app.txt_log.get("1.0", "end")
check("the run survived warnings/drops and said so in the log", "Bağlantı sorunu" in log or "yavaşlama uyarısı" in log)
check("no unexpected-error entries", "Beklenmeyen hata" not in log)
print("elapsed %.1fs" % (time.time() - t0))
root.destroy(); print(f"ALL OK ({n} checks)")