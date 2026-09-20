import os, sys
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import sys, time, types
pass
import tkinter as tk
from tkinter import ttk
import igdm_app as g
import tempfile as _tf, os as _os
_d = _tf.mkdtemp()
g.SETTINGS_FILE = _os.path.join(_d, "s.json"); g.PROTECTED_FILE = _os.path.join(_d, "p.json"); g.LOG_FILE = _os.path.join(_d, "l.log")
for _p in g.PROFILES.values(): _p.update(unsend=(0, 0), hide=(0, 0), rest=(0, 0), batch=10**6)
g.SOFT_PAUSE = (0, 0)

real_sleep = time.sleep
g.time.sleep = lambda s: real_sleep(0.01)
calls = []

class FakeClient:
    uuid = "u"; token = "t"
    def __init__(self): self.challenge_code_handler = None; self.change_password_handler = None
    def login_by_sessionid(self, sid): pass
    def account_info(self): return types.SimpleNamespace(username="me", pk=7)
    def direct_message_unsend(self, thread_id, msg_id): calls.append(("unsend", str(msg_id))); return True
    def private_request(self, ep, params=None, data=None, with_signature=True):
        if ep == "direct_v2/inbox/":
            return {"inbox": {"has_older": False, "threads": [
                {"thread_id": "100", "users": [{"pk": 9, "username": "ayse"}], "items": [{"text": "selam", "item_type": "text"}]},
                {"thread_id": "200", "users": [{"pk": 8, "username": "ali"}], "items": []}]}}
        if ep == "direct_v2/threads/100/":
            if (params or {}).get("cursor") == "c2":
                return {"thread": {"users": [{"pk": 9, "username": "ayse"}], "has_older": False, "items": [
                    {"item_id": "5", "user_id": 7, "text": "eski benim", "timestamp": 1700000000000000, "item_type": "text"}]}}
            return {"thread": {"users": [{"pk": 9, "username": "ayse"}], "has_older": True, "oldest_cursor": "c2", "items": [
                {"item_id": "1", "user_id": 7, "text": "test benim bir", "timestamp": 1700000300000000, "item_type": "text"},
                {"item_id": "2", "user_id": 9, "text": "test onun mesajı", "timestamp": 1700000200000000, "item_type": "text"},
                {"item_id": "3", "user_id": 7, "text": "benim iki", "timestamp": 1700000100000000, "item_type": "text"}]}}
        if ep.endswith("/hide/"):
            calls.append(("hide", ep.split("/")[2])); return {"status": "ok"}
        raise AssertionError(ep)

g.Client = FakeClient; g.load_session = lambda *a, **k: False
g.ui.showinfo = lambda *a, **k: calls.append(("info", a[1] if len(a) > 1 else ""))
g.ui.showwarning = lambda *a, **k: None
g.ui.askyesno = lambda *a, **k: True
root = tk.Tk(); app = g.App(root)

def pump(cond, t=20):
    end = time.time() + t
    while time.time() < end:
        root.update()
        if cond(): return
        real_sleep(0.02)
    raise TimeoutError

app.var_sid.set("1234567890:" + "A" * 40); app.do_login_session()
pump(lambda: app.client is not None)
pump(lambda: len(app.tv_threads.get_children()) == 2)

# 1) choosing a chat loads the messages automatically (no button press)
app.tv_threads.selection_set("100"); app.choose_thread()
pump(lambda: not app.busy and len(app.tv_msgs.get_children()) == 4)
ids = set(app.tv_msgs.get_children()); assert ids == {"1", "2", "3", "5"}, ids
assert set(app.found) == {"1", "3", "5"}, app.found
assert app.tv_msgs.item("2", "values")[1] == "ayse" and app.tv_msgs.item("1", "values")[1] == "Ben"
assert "other" in app.tv_msgs.item("2", "tags") and "other" not in app.tv_msgs.item("1", "tags")
assert set(app.tv_msgs.selection()) == {"1", "3", "5"}
print("PASS auto-load on chat select: 4 messages (both sides), other side greyed, only own selected")

# 2) selecting the other person's row too: it is skipped
app.tv_msgs.selection_set(["1", "2"]); app.delete_selected()
pump(lambda: not app.busy and ("unsend", "1") in calls)
pump(lambda: not app.busy)
assert [c for c in calls if c[0] == "unsend"] == [("unsend", "1")], calls
assert "2" in app.tv_msgs.get_children() and "1" not in app.tv_msgs.get_children()
print("PASS unsend skips the other person's message")

# 3) keyword filter shows matches from both sides
calls.clear(); app.var_kw.set("test"); app.find_messages()
pump(lambda: not app.busy and len(app.tv_msgs.get_children()) >= 1)
assert set(app.tv_msgs.get_children()) == {"1", "2"}, app.tv_msgs.get_children()   # both contain "test"
print("PASS keyword filter (fake server still returns unsent msg 1; matches:", sorted(app.tv_msgs.get_children()), ")")

# 4) delete whole chat (hide only)
def click(dlg, text, toggle_first=False):
    def walk(w):
        for c in w.winfo_children():
            yield c; yield from walk(c)
    if toggle_first:
        for w in walk(dlg):
            if isinstance(w, ttk.Checkbutton): w.invoke()
    for w in walk(dlg):
        if isinstance(w, tk.Button) and w.cget("text") == text: w.invoke(); return
    raise AssertionError("button not found")

calls.clear(); app.var_kw.set(""); app.find_messages(); pump(lambda: not app.busy and len(app.tv_msgs.get_children()) == 4)
app.root.wait_window = lambda dlg: click(dlg, "Sohbeti sil")
app.delete_thread()
pump(lambda: ("hide", "100") in calls and app.thread_id is None)
assert [c for c in calls if c[0] == "unsend"] == [], calls
assert "100" not in app.tv_threads.get_children() and str(app.nb.tab(2, "state")) == "normal" and app.thread_id is None
assert str(app.nb.index(app.nb.select())) == "1"
print("PASS delete chat only: hide called, no unsends, chat removed from list, back to chat list")

# 5) delete whole chat, unsending own messages first
app.thread_id = None
app.tv_threads.selection_set("200"); app.choose_thread(); pump(lambda: not app.busy)
app.thread_id = "100"; app.thread_name = "ayse"; app.nb.tab(2, state="normal")
app.threads.append({"thread_id": "100", "users": [], "items": []})
app.find_messages(); pump(lambda: not app.busy and len(app.tv_msgs.get_children()) == 4)
calls.clear()
app.root.wait_window = lambda dlg: click(dlg, "Sohbeti sil", toggle_first=True)
app.delete_thread()
pump(lambda: ("hide", "100") in calls and app.thread_id is None, 30)
seq = [c for c in calls if c[0] in ("unsend", "hide")]
assert seq == [("unsend", "1"), ("unsend", "3"), ("unsend", "5"), ("hide", "100")], seq
print("PASS delete chat with unsend-first: own messages unsent, THEN chat hidden")
root.destroy(); print("ALL OK")


