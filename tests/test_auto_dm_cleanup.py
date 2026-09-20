import os, sys
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import sys, time, types, random
pass
import tkinter as tk
import igdm_app as g
import tempfile as _tf, os as _os
_d = _tf.mkdtemp()
g.SETTINGS_FILE = _os.path.join(_d, "s.json"); g.PROTECTED_FILE = _os.path.join(_d, "p.json"); g.LOG_FILE = _os.path.join(_d, "l.log")
for _p in g.PROFILES.values(): _p.update(unsend=(0, 0), hide=(0, 0), rest=(0, 0), batch=10**6)
g.SOFT_PAUSE = (0, 0)
from instagrapi.exceptions import PleaseWaitFewMinutes, FeedbackRequired

real_sleep = time.sleep
g.time.sleep = lambda s: real_sleep(0.005)
calls = []
state = {"limit_on_hide_n": None, "hides": 0}

# 30 threads; t1 is newest, t30 oldest. t25 is pinned. Served shuffled to prove we sort ourselves.
THREADS = [{"thread_id": str(i), "users": [{"pk": 100 + i, "username": f"user{i}"}],
            "last_activity_at": (1700000000 - i * 1000) * 1_000_000, "is_pin": i == 25, "items": []} for i in range(1, 31)]
SERVED = THREADS[:]; random.Random(1).shuffle(SERVED)

class FakeClient:
    uuid = "u"; token = "t"
    def __init__(self): self.challenge_code_handler = None; self.change_password_handler = None
    def login_by_sessionid(self, sid): pass
    def account_info(self): return types.SimpleNamespace(username="me", pk=7)
    def direct_message_unsend(self, thread_id, msg_id): calls.append(("unsend", str(thread_id), str(msg_id))); return True
    def private_request(self, ep, params=None, data=None, with_signature=True):
        if ep == "direct_v2/inbox/":
            start = int((params or {}).get("cursor") or 0)
            page = SERVED[start:start + 20]
            return {"inbox": {"threads": page, "has_older": start + 20 < len(SERVED), "oldest_cursor": str(start + 20)}}
        if ep.startswith("direct_v2/threads/") and ep.endswith("/hide/"):
            state["hides"] += 1
            if state["limit_on_hide_n"] and state["hides"] == state["limit_on_hide_n"]:
                raise state.get("exc", FeedbackRequired)("feedback_required")
            calls.append(("hide", ep.split("/")[2])); return {"status": "ok"}
        if ep.startswith("direct_v2/threads/") and ep.endswith("/"):
            tid = ep.split("/")[2]
            return {"thread": {"has_older": False, "items": [
                {"item_id": f"{tid}a", "user_id": 7, "text": "mine", "timestamp": 1},
                {"item_id": f"{tid}b", "user_id": 5, "text": "theirs", "timestamp": 2},
                {"item_id": f"{tid}c", "user_id": 7, "text": "mine2", "timestamp": 3}]}}
        raise AssertionError(ep)

g.Client = FakeClient; g.load_session = lambda *a, **k: False
g.ui.showinfo = lambda *a, **k: calls.append(("info",))
g.ui.showwarning = lambda *a, **k: None
answers = {"v": "SİL"}
g.ui.askstring = lambda *a, **k: answers["v"]
root = tk.Tk(); app = g.App(root)

def pump(cond, t=30):
    end = time.time() + t
    while time.time() < end:
        root.update()
        if cond(): return
        real_sleep(0.01)
    raise TimeoutError

app.var_sid.set("1234567890:" + "A" * 40); app.do_login_session()
pump(lambda: app.client is not None); pump(lambda: not app.busy)
assert str(app.nb.tab(3, "state")) == "normal"

# scan + plan
app.auto_scan(); pump(lambda: not app.busy and app.auto_threads)
assert len(app.auto_threads) == 30 and [t["thread_id"] for t in app.auto_threads][:3] == ["1", "2", "3"]
keep_ids = {str(t["thread_id"]) for t in app.auto_plan()[0]}
todo_ids = [str(t["thread_id"]) for t in app.auto_todo]
assert keep_ids == {str(i) for i in range(1, 21)} | {"25"}, keep_ids
assert todo_ids == [str(i) for i in range(21, 31) if i != 25], todo_ids
print("PASS scan across 2 pages, sorted by recency; keep newest 20 + pinned #25; plan deletes", len(todo_ids))
assert str(app.btn_autorun.cget("state")) == "normal"

# changing the number re-plans; pins off
app.var_keep.set(10); app.var_keep_pins.set(False); app.auto_render()
assert len(app.auto_todo) == 20; app.var_keep.set(20); app.var_keep_pins.set(True); app.auto_render()
print("PASS changing keep-count / pin option re-plans")

# decline confirmation -> nothing deleted
answers["v"] = "hayır"; calls.clear(); app.auto_start(); root.update()
assert not [c for c in calls if c[0] == "hide"] and not app.busy
print("PASS wrong/declined confirmation deletes nothing")

# confirm -> hides exactly the plan, nothing else
answers["v"] = "SİL"; app.auto_start()
pump(lambda: not app.busy and ("info",) in calls)
hidden = [c[1] for c in calls if c[0] == "hide"]
assert hidden == todo_ids, hidden
assert not [c for c in calls if c[0] == "unsend"]
assert len(app.auto_threads) == 21 and app.auto_todo == []
assert str(app.btn_autorun.cget("state")) == "disabled"
print("PASS auto cleanup hid exactly the 9 planned chats (newest kept, pinned kept); no unsends; plan now empty")

# Instagram rate-limit stops immediately and keeps the rest
SERVED[:] = [t for t in THREADS]; random.Random(2).shuffle(SERVED)
state.update(limit_on_hide_n=None, hides=0); calls.clear()
app.auto_scan(); pump(lambda: not app.busy and app.auto_threads)
state["hides"] = 0; state["limit_on_hide_n"] = 3
app.auto_start(); pump(lambda: not app.busy and ("info",) in calls)
assert len([c for c in calls if c[0] == "hide"]) == 2 and state["hides"] == 3, (calls, state)
print("PASS HARD warning (feedback_required) on 3rd chat: stopped at once (2 deleted, rest untouched)")

# unsend-first: own messages unsent before hide
state["limit_on_hide_n"] = None; calls.clear()
SERVED[:] = [t for t in THREADS]; app.auto_scan(); pump(lambda: not app.busy and app.auto_threads)
app.var_keep.set(29); app.var_keep_pins.set(False); app.auto_render(); assert len(app.auto_todo) >= 1
app.var_unsend_first.set(True); app.auto_start(); pump(lambda: not app.busy and ("info",) in calls)
seq = [c[0] for c in calls if c[0] in ("unsend", "hide")]
assert seq[-1] == "hide" and seq.count("unsend") == 2 and seq[:2] == ["unsend", "unsend"], seq
print("PASS unsend-first: own 2 messages unsent (not the other side's), then chat hidden")
root.destroy(); print("ALL OK")


