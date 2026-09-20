import os, sys
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import sys, time, types, os, tempfile, subprocess, threading
pass
ROOT = SRC
import tkinter as tk
import igdm_app as g
import igdm_common as C
import igdm_core

D = tempfile.mkdtemp()
g.SETTINGS_FILE = os.path.join(D, "s.json"); g.PROTECTED_FILE = os.path.join(D, "p.json"); g.LOG_FILE = os.path.join(D, "l.log"); g.KEEP_FILE = os.path.join(D, "k.json")
for _p in g.PROFILES.values(): _p.update(unsend=(0, 0), hide=(0, 0), story=(0, 0), unblock=(0, 0), unlike=(0, 0), rest=(0, 0), batch=10**6)
g.SOFT_PAUSE = (0, 0); g.NET_BACKOFF = (0, 0, 0, 0)
real_sleep = time.sleep; g.time.sleep = lambda s: real_sleep(0.002)
n_ok = 0
def check(name, cond):
    global n_ok
    assert cond, "FAIL: " + name
    n_ok += 1; print("PASS", name)

# ---------------------------------------------------------------- pure classification
check("network errors are recognised", all(C.is_network_error(e) for e in (ConnectionError("x"), TimeoutError("t"), Exception("Max retries exceeded"), Exception("curl: (28) Operation timed out"))))
check("Instagram verdicts and the security guard are NOT network errors", not any(C.is_network_error(e) for e in (
    igdm_core.BlockedDestination("blocked"), Exception("feedback_required"), Exception("Please wait a few minutes"), ValueError("bad value"))))
check("friendly() explains a connection problem in Turkish", "internet bağlantını" in C.friendly(ConnectionError("boom")))

# ---------------------------------------------------------------- light start-up path
code = "import sys; sys.path.insert(0, r'%s'); import igdm_launcher, igdm_intro, igdm_icon, igdm_meta; print('instagrapi' in sys.modules, 'pydantic' in sys.modules, 'igdm_app' in sys.modules)" % ROOT
out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60).stdout.strip()
check("launcher + intro import WITHOUT loading instagrapi/pydantic/the GUI (%s)" % out, out == "False False False")

# ---------------------------------------------------------------- app-level robustness
state = {"fail": [], "calls": 0}
class FakeClient:
    uuid = "u"; token = "t"; user_id = "7"
    def __init__(self): self.challenge_code_handler = None; self.change_password_handler = None
    def login_by_sessionid(self, sid): pass
    def account_info(self): return types.SimpleNamespace(username="tester", pk=7)
    def private_request(self, ep, params=None, data=None, with_signature=True):
        if ep == "direct_v2/inbox/": return {"inbox": {"threads": [], "has_older": False}}
        state["calls"] += 1
        if state["fail"]:
            e = state["fail"].pop(0)
            if e: raise e
        return {"status": "ok"}
g.Client = FakeClient; g.load_session = lambda *a, **k: False
infos = []; g.ui.showinfo = lambda *a, **k: infos.append(a[1] if len(a) > 1 else ""); g.ui.showwarning = lambda *a, **k: None

root = tk.Tk(); app = g.App(root)
def pump(cond=lambda: False, t=15):
    end = time.time() + t
    while time.time() < end:
        root.update()
        if cond(): return True
        real_sleep(0.01)
    return cond()
app.var_sid.set("1234567890:" + "A" * 40); app.do_login_session(); pump(lambda: app.client is not None); pump(lambda: not app.busy)

check("after login every page is enabled (incl. Mesajlar)", all(str(app.nb.tab(i, "state")) == "normal" for i in range(7)))
app.nb.select(2); pump(t=0.05)
check("Mesajlar page opens with no chat selected and explains what to do", app.lbl_thread.cget("text") == "Sohbet: seçilmedi" and "sohbet seçilmedi" in app.hint_msgs.cget("text").lower())
app.find_messages(); check("'Yükle / Ara' with no chat gives a hint instead of failing", "sohbet seç" in app.lbl_prog.cget("text").lower() and not app.busy)
app.delete_thread(); app.delete_selected(); check("delete actions with no chat are harmless", not app.busy)
app.btn_pick.invoke(); pump(t=0.05); check("'Sohbet seç →' button jumps to the chat list", app.nb.index(app.nb.select()) == 1)

# crash in a worker: logged, traceback in file, UI unlocked
app.set_busy(True); app.pb.configure(mode="indeterminate"); app.pb.start(10)
def boom(): raise RuntimeError("kasıtlı test hatası")
app.run_bg(boom); pump(lambda: not app.busy)
check("worker crash: UI unlocked (not stuck 'busy')", not app.busy and str(app.pb.cget("mode")) == "determinate")
log = app.txt_log.get("1.0", "end"); check("worker crash: message shown in the log", "Beklenmeyen hata" in log and "kasıtlı test hatası" in log)
check("worker crash: traceback written to the log file", "TRACEBACK" in open(g.LOG_FILE, encoding="utf-8").read() and "boom" in open(g.LOG_FILE, encoding="utf-8").read())
root.after(0, lambda: 1 / 0); pump(t=0.3)
check("error inside a Tk callback is logged, app keeps running", "division by zero" in app.txt_log.get("1.0", "end") or "ZeroDivisionError" in open(g.LOG_FILE, encoding="utf-8").read())

# connectivity drops: retried transparently
res = {}
def call(): res["v"] = app.guarded(lambda: app.client.private_request("x/y/"))
state.update(fail=[ConnectionError("Wi-Fi gitti"), TimeoutError("timed out")], calls=0)
th = threading.Thread(target=call); th.start(); pump(lambda: not th.is_alive()); th.join()
check("2 dropped connections -> retried and succeeded (3 requests)", res.get("v", {}).get("status") == "ok" and state["calls"] == 3)
check("the retries were announced in the log", pump(lambda: "Bağlantı sorunu" in app.txt_log.get("1.0", "end"), 5))   # log lines travel through the UI queue
res.clear(); state.update(fail=[ConnectionError("down")] * 10, calls=0)
def call2():
    try: app.guarded(lambda: app.client.private_request("x/y/"))
    except Exception as e: res["err"] = e
th = threading.Thread(target=call2); th.start(); pump(lambda: not th.is_alive()); th.join()
check("connection stays down -> gives up after %d retries with the original error" % len(g.NET_BACKOFF), isinstance(res.get("err"), ConnectionError) and state["calls"] == len(g.NET_BACKOFF) + 1)
res.clear(); state.update(fail=[igdm_core.BlockedDestination("evil.com")], calls=0)
th = threading.Thread(target=call2); th.start(); pump(lambda: not th.is_alive()); th.join()
check("security-guard block is NOT retried", isinstance(res.get("err"), igdm_core.BlockedDestination) and state["calls"] == 1)
# stop while waiting for the network
g.NET_BACKOFF = (30, 30); res.clear(); state.update(fail=[ConnectionError("down")] * 5, calls=0); app.stop_event.clear()
def call3():
    try: app.guarded(lambda: app.client.private_request("x/y/"))
    except BaseException as e: res["err"] = e
g.time.sleep = lambda s: real_sleep(0.02)
th = threading.Thread(target=call3); th.start(); pump(t=0.3); app.stop_event.set(); pump(lambda: not th.is_alive()); th.join()
check("Stop during a connection wait ends it immediately", isinstance(res.get("err"), g.StopRequested))
root.destroy()
print(f"ALL OK ({n_ok} checks)")
