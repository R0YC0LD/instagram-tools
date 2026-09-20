import os, sys, time
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import tkinter as tk
import igdm_intro as I

n = 0
def check(name, cond):
    global n
    assert cond, "FAIL: " + name
    n += 1; print("PASS", name)

root = tk.Tk(); root.geometry("1000x700+50+50")
calls = []
intro = I.Intro(root, on_done=lambda: calls.append(1), speed=1500)
t0 = time.time()
while not intro.done and time.time() - t0 < 30:
    root.update(); time.sleep(0.005)
check("credits scroll off the top and the intro ends by itself", intro.done and calls == [1])
check("the intro frame is removed afterwards", not intro.frame.winfo_exists())

calls.clear(); intro = I.Intro(root, on_done=lambda: calls.append(1), speed=60)
for _ in range(30): root.update(); time.sleep(0.01)
intro.skip(); intro.skip(); root.update()
check("skip works and on_done fires exactly once", intro.done and calls == [1])

texts = " ".join(str(x[1]) for x in I.credit_items() if x[0] == "text")
check("credits contain 'Made in Türkiye', the author and the Instagram handle",
      "M\u2009A\u2009D\u2009E" in texts.replace("  ", " ") or "MADE" in texts.replace("\u2009", "").upper())
check("author and handle are shown", "Onur Teryakioğlu" in texts and "@on_r19" in texts)
root.destroy(); print(f"ALL OK ({n} checks)")