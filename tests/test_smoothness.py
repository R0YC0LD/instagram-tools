"""Smoothness: the UI must keep animating (no freezes) while workers hammer it, and the intro must hit a good frame rate."""
import os, sys, time, threading, tempfile, statistics
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import tkinter as tk
import igdm_perf as perf
import igdm_intro as I
import igdm_app as g

D = tempfile.mkdtemp()
g.SETTINGS_FILE = os.path.join(D, "s.json"); g.PROTECTED_FILE = os.path.join(D, "p.json"); g.LOG_FILE = os.path.join(D, "l.log"); g.KEEP_FILE = os.path.join(D, "k.json")
g.load_session = lambda *a, **k: False
n = 0
def check(name, cond, detail=""):
    global n
    assert cond, "FAIL: " + name + (f"  -> {detail}" if detail else "")
    n += 1; print("PASS", name)

hz = perf.refresh_rate_hz()
check(f"display refresh rate is read ({hz} Hz) and the frame time is sane ({perf.frame_ms()} ms)", 30 <= hz <= 360 and 4 <= perf.frame_ms() <= 33)

# ------------------------------------------------------------------------------- intro frame rate
best = 0.0
for attempt in range(3):                  # a one-off OS hiccup (antivirus scan, ...) must not fail the test; a real regression fails all 3
    root = tk.Tk(); root.geometry("1000x700+30+30")
    intro = I.Intro(root, speed=40)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 2.0:
        root.update(); time.sleep(0.001)
    best = max(best, intro._frames / 2.0)
    intro.finish(); root.destroy()
    if best >= 45: break
check(f"intro animates at a high frame rate (%.0f fps on a {hz} Hz display)" % best, best >= 45, f"{best:.0f} fps")
# ------------------------------------------------------------------------------- UI stays responsive under load
root = tk.Tk(); app = g.App(root)
def pump(t):
    end = time.time() + t
    while time.time() < end: root.update(); time.sleep(0.0005)

gaps, last = [], [time.perf_counter()]
def heartbeat():
    now = time.perf_counter(); gaps.append((now - last[0]) * 1000); last[0] = now
    root.after(app.frame_ms, heartbeat)
root.after(app.frame_ms, heartbeat)

durations = []
orig_poll = app._poll
def timed_poll():
    t = time.perf_counter(); orig_poll(); durations.append((time.perf_counter() - t) * 1000)
app._poll = timed_poll
root.after_cancel  # (the original poll is already scheduled; the next one re-schedules through the patched name)

burst = 6000
def worker():
    for i in range(burst):
        app.post(lambda i=i: app.lbl_prog.configure(text=f"işlem {i}"))          # 6000 tiny UI updates at once
        if i % 500 == 0:
            app.post(lambda i=i: app.log(f"[{i}/{burst}] tamam"))
th = threading.Thread(target=worker); th.start()
pump(0.3); gaps.clear(); durations.clear(); last[0] = time.perf_counter()
pump(3.0); th.join()
gaps_sorted = sorted(gaps)
p99 = gaps_sorted[int(len(gaps_sorted) * 0.99) - 1]
check("a burst of %d UI updates from a worker is processed in small slices" % burst, durations and max(durations) < 40, f"longest slice {max(durations):.1f} ms" if durations else "no polls")
check("no UI freeze: p99 frame gap %.0f ms, worst %.0f ms" % (p99, max(gaps)), p99 < 60 and max(gaps) < 250, f"p99={p99:.0f} max={max(gaps):.0f}")
check("all queued updates were eventually applied", app.q.empty() and app.lbl_prog.cget("text") == f"işlem {burst - 1}")

# ------------------------------------------------------------------------------- logging does not block the UI
t = time.perf_counter()
for i in range(3000): app.log(f"satır {i}")
ui_ms = (time.perf_counter() - t) * 1000
app.flush_log(10)
lines = open(g.LOG_FILE, encoding="utf-8").read().count("satır ")
check("3000 log() calls: file writing happens off the UI thread (UI cost %.0f ms) and no line is lost" % ui_ms, lines >= 3000 and ui_ms < 2500, f"{lines} lines, {ui_ms:.0f} ms")
shown = int(app.txt_log.index("end-1c").split(".")[0])
check("the on-screen log is trimmed (%d lines shown) so it never slows down over hours" % shown, shown <= 1600, str(shown))

# ------------------------------------------------------------------------------- sidebar repaint is cached
sb = app.sidebar
calls = []
row = sb.rows[3]["row"]; orig_cfg = row.configure
row.configure = lambda *a, **k: (calls.append(1), orig_cfg(*a, **k))[1]
sb.refresh(); sb.refresh(); sb.refresh()
check("sidebar: repeated refreshes with no state change cause zero Tk calls", calls == [])
app.nb.tab(3, state="normal"); calls.clear(); sb._hover(3, True); ok1 = len(calls); sb._hover(3, False)
check("sidebar: hover repaints only the hovered row", ok1 >= 1)
root.destroy(); print(f"ALL OK ({n} checks)")
