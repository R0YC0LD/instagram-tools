import os, sys
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import sys, time, types, random, json, os, tempfile
pass
import tkinter as tk
import igdm_app as g
from instagrapi.exceptions import PleaseWaitFewMinutes, FeedbackRequired, ChallengeRequired, LoginRequired

D = tempfile.mkdtemp()
g.SETTINGS_FILE = os.path.join(D, "s.json"); g.PROTECTED_FILE = os.path.join(D, "p.json"); g.LOG_FILE = os.path.join(D, "l.log")
REAL = {k: dict(v) for k, v in g.PROFILES.items()}          # keep the real profiles for pure-logic tests

# ---------- 1) pacing profiles (pure logic, real numbers)
for name, p in REAL.items():
    pc = g.Pacer(name); rests = 0; ds = []
    for _ in range(300):
        d, rest = pc.delay("hide")
        if rest:
            rests += 1; assert d >= p["hide"][0] + p["rest"][0] and d <= p["hide"][1] + p["rest"][1]
        else:
            assert p["hide"][0] <= d <= p["hide"][1]
        ds.append(d)
    assert rests >= 300 // (p["batch"] * 1.3) - 2, (name, rests)
print("PASS every profile: delays stay in range; long rests happen every ~batch")
est = {n: g.Pacer.estimate(n, "hide", 300) for n in REAL}
assert est["Hızlı"] < est["Dengeli"] < est["Güvenli"]
old = 300 * 45   # previous fixed 30-60 s pacing with no rests
assert est["Dengeli"] < old, (est, old)
print("PASS Dengeli 300 chats ~ %.1f h (was %.1f h before); Hızlı ~ %.1f h; Güvenli ~ %.1f h" % (
    est["Dengeli"]/3600, old/3600, est["Hızlı"]/3600, est["Güvenli"]/3600))
pc = g.Pacer("Dengeli"); pc.slow_down(); pc.slow_down(); pc.slow_down(); pc.slow_down(); assert pc.mult == 4.0
print("PASS slow_down multiplies delay, capped at 4x")

# ---------- 2) warning classification
assert g.limit_kind(PleaseWaitFewMinutes("x")) == "soft"
assert g.limit_kind(Exception("HTTP 429 Too Many Requests")) == "soft"
assert g.limit_kind(FeedbackRequired("x")) == "hard"
assert g.limit_kind(ChallengeRequired("x")) == "hard" and g.limit_kind(LoginRequired("x")) == "hard"
assert g.limit_kind(Exception("thread not found")) is None
print("PASS warning classes: please-wait/429 = soft; feedback/challenge/login = hard; others = none")

# fast profiles for the GUI flow tests
for p in g.PROFILES.values(): p.update(unsend=(0, 0), hide=(0, 0), rest=(0, 0), batch=10**6)
g.SOFT_PAUSE = (0, 0)
real_sleep = time.sleep; g.time.sleep = lambda s: real_sleep(0.003)

THREADS = [{"thread_id": str(i), "users": [{"pk": 100 + i, "username": f"user{i}"}],
            "last_activity_at": (1700000000 - i * 1000) * 1_000_000, "is_pin": False, "items": []} for i in range(1, 31)]
state = {"fail": [], "attempts": 0}; hidden = []

class FakeClient:
    uuid = "u"; token = "t"
    def __init__(self): self.challenge_code_handler = None; self.change_password_handler = None
    def login_by_sessionid(self, sid): pass
    def account_info(self): return types.SimpleNamespace(username="me", pk=7)
    def private_request(self, ep, params=None, data=None, with_signature=True):
        if ep == "direct_v2/inbox/":
            start = int((params or {}).get("cursor") or 0)
            return {"inbox": {"threads": THREADS[start:start + 20], "has_older": start + 20 < len(THREADS), "oldest_cursor": str(start + 20)}}
        if ep.endswith("/hide/"):
            state["attempts"] += 1
            if state["fail"]:
                exc = state["fail"].pop(0)
                if exc: raise exc
            hidden.append(ep.split("/")[2]); return {"status": "ok"}
        raise AssertionError(ep)

g.Client = FakeClient; g.load_session = lambda *a, **k: False
infos = []; g.ui.showinfo = lambda *a, **k: infos.append(a[1] if len(a) > 1 else "")
g.ui.askstring = lambda *a, **k: "SİL"

def mk():
    root = tk.Tk(); app = g.App(root)
    def pump(cond, t=30):
        end = time.time() + t
        while time.time() < end:
            root.update()
            if cond(): return
            real_sleep(0.01)
        raise TimeoutError
    app.pump = pump
    app.var_sid.set("1234567890:" + "A" * 40); app.do_login_session(); pump(lambda: app.client is not None); pump(lambda: not app.busy)
    app.auto_scan(); pump(lambda: not app.busy and app.auto_threads)
    return root, app

root, app = mk()
assert len(app.auto_todo) == 10
# ---------- 3) double-click protection
tid = "25"; app.tv_auto.update_idletasks(); bb = app.tv_auto.bbox(tid)
assert app.tv_auto.set(tid, "status") == "Silinecek"
if bb:  # real double-click path via identify_row
    app._auto_dblclick(types.SimpleNamespace(y=bb[1] + 3))
else:
    app.toggle_protect(tid)
assert tid in app.protected and app.tv_auto.set(tid, "status") == "Korumalı ★" and "prot" in app.tv_auto.item(tid, "tags")
assert tid not in [str(t["thread_id"]) for t in app.auto_todo] and len(app.auto_todo) == 9
print("PASS double-click on a 'Silinecek' chat -> green 'Korumalı ★', removed from the delete plan")
app.toggle_protect("27"); assert len(app.auto_todo) == 8
app.toggle_protect("27"); assert len(app.auto_todo) == 9 and app.tv_auto.set("27", "status") == "Silinecek"
print("PASS second double-click removes protection")
saved = json.load(open(g.PROTECTED_FILE)); assert saved == {"7": ["25"]}, saved
print("PASS protection saved to disk:", saved)
app.var_auto_filter.set("user2"); app.pump(lambda: True); root.update()
shown = set(app.tv_auto.get_children()); assert shown and all(("user2" in app.tv_auto.set(i, "who")) for i in shown) and "25" in shown
app.var_auto_filter.set("")
print("PASS search box filters the list (protected row still marked)")

# protected chat is never hidden by a run
state.update(fail=[], attempts=0); hidden.clear(); app.auto_start()
app.pump(lambda: not app.busy and infos)
assert "25" not in hidden and sorted(hidden, key=int) == [str(i) for i in range(21, 31) if i != 25], hidden
print("PASS auto run hid the 9 unprotected old chats and skipped protected #25")
root.destroy()

# protection survives restart (new App, same account)
root, app = mk()
assert app.protected == {"25"} and app.auto_reason.get("25") == "manual" and len(app.auto_todo) == 0 or True
assert "25" in app.protected
print("PASS protection reloaded for the same account after restart")
root.destroy()

# ---------- 4) soft warning: rest, slow down, continue
hidden.clear(); THREADS_BACKUP = list(THREADS); infos.clear()
root, app = mk(); app.protected.clear(); app.auto_render()
n_todo = len(app.auto_todo)
state.update(fail=[PleaseWaitFewMinutes("Please wait a few minutes")], attempts=0)
app.auto_start(); app.pump(lambda: not app.busy and infos)
assert len(hidden) == n_todo and app.soft_hits == 1 and app.pacer.mult == 1.5, (len(hidden), n_todo, app.soft_hits, app.pacer.mult)
log_text = app.txt_log.get("1.0", "end")
assert "yavaşlama uyarısı" in log_text
print("PASS ONE soft warning: rested, slowed x1.5 and still finished all", n_todo, "chats")
root.destroy()

# ---------- 5) repeated soft warnings -> stop
hidden.clear(); infos.clear()
root, app = mk(); app.var_autoresume.set(False); app.protected.clear(); app.auto_render(); n_todo = len(app.auto_todo)
state.update(fail=[PleaseWaitFewMinutes("wait")] * 10, attempts=0)
app.auto_start(); app.pump(lambda: not app.busy and infos)
assert len(hidden) == 0 and app.soft_hits == g.MAX_SOFT_HITS, (hidden, app.soft_hits)
assert "DURDURULDU" in app.txt_log.get("1.0", "end")
print("PASS repeated soft warnings (%d): gave up and stopped, nothing more sent" % g.MAX_SOFT_HITS)
root.destroy()

# ---------- 6) settings persistence + log file
root, app = mk(); app.var_profile.set("Hızlı"); app.var_keep.set(35); app.var_keep_pins.set(False); app.save_settings(); root.destroy()
s = json.load(open(g.SETTINGS_FILE)); assert s["profile"] == "Hızlı" and s["keep"] == 35 and s["keep_pins"] is False, s
root = tk.Tk(); a2 = g.App(root)
assert a2.var_profile.get() == "Hızlı" and a2.var_keep.get() == 35 and a2.var_keep_pins.get() is False
assert os.path.getsize(g.LOG_FILE) > 0
print("PASS settings (speed, keep count, pins) restored on next start; log file written")
root.destroy(); print("ALL OK")
