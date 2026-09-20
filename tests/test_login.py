import os, sys
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import ctypes; ctypes.windll.shcore.SetProcessDpiAwareness(1)
import sys, os, time, types
pass
import tkinter as tk
from PIL import ImageGrab
import igdm_app as g
import tempfile as _tf, os as _os
_d = _tf.mkdtemp()
g.SETTINGS_FILE = _os.path.join(_d, "s.json"); g.PROTECTED_FILE = _os.path.join(_d, "p.json"); g.LOG_FILE = _os.path.join(_d, "l.log")
for _p in g.PROFILES.values(): _p.update(unsend=(0, 0), hide=(0, 0), rest=(0, 0), batch=10**6)
g.SOFT_PAUSE = (0, 0)
from instagrapi.exceptions import ClientError

got = {}
class FakeClient:
    def __init__(self): self.challenge_code_handler = None; self.change_password_handler = None
    def login(self, *a, **k): raise ClientError("Your version of Instagram is out of date. Please upgrade your app to log in to Instagram.")
    def login_by_sessionid(self, sid): got["sid"] = sid
    def account_info(self): return types.SimpleNamespace(username="testuser", pk=7)
    def private_request(self, ep, params=None, **k): return {"inbox": {"threads": [], "has_older": False}}
    def get_settings(self): return {}
g.Client = FakeClient; g.load_session = lambda *a, **k: False
warn = []
g.ui.showwarning = lambda *a, **k: warn.append(a)
root = tk.Tk(); app = g.App(root)
root.geometry("940x720+40+40"); root.attributes("-topmost", True); root.lift(); root.focus_force()
def pump(cond, t=10):
    end = time.time() + t
    while time.time() < end:
        root.update()
        if cond(): return
        time.sleep(0.02)
    raise TimeoutError

# password login -> friendly guidance about the out-of-date error
app.var_user.set("u"); app.var_pass.set("p"); app.do_login()
pump(lambda: "Tarayıcı oturumuyla" in app.lbl_login.cget("text") and not app.busy)
print("PASS out-of-date error explained with pointer to option B")
# bad sessionid rejected client-side
app.var_sid.set("abc"); app.do_login_session(); root.update()
assert warn and app.client is None; print("PASS invalid sessionid rejected")
# good sessionid (URL-encoded colon, pasted with quotes)
app.var_sid.set('"1234567890%3AABCDEFGHIJKLMNOPQRSTUVWXYZ012345%3A1%3AAbc"'); app.do_login_session()
pump(lambda: app.client is not None)
assert got["sid"] == "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ012345:1:Abc", got
assert app.var_sid.get() == ""
print("PASS sessionid login ->", app.lbl_account.cget("text"), "; sessionid decoded and field cleared")
root.destroy()

