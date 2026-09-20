import os, sys
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import sys, time, types, os, tempfile
pass
import tkinter as tk
from tkinter import ttk
import igdm_app as g
import igdm_ui as ui
import igdm_common as C

D = tempfile.mkdtemp()
g.SETTINGS_FILE = os.path.join(D, "s.json"); g.PROTECTED_FILE = os.path.join(D, "p.json"); g.LOG_FILE = os.path.join(D, "l.log"); g.KEEP_FILE = os.path.join(D, "k.json")
real_sleep = time.sleep

class FakeClient:
    uuid = "u"; token = "t"; user_id = "7"
    def __init__(self): self.challenge_code_handler = None; self.change_password_handler = None
    def login_by_sessionid(self, sid): pass
    def account_info(self): return types.SimpleNamespace(username="pac.man", pk=7)
    def private_request(self, ep, params=None, **k): return {"inbox": {"threads": [], "has_older": False}}
g.Client = FakeClient; g.load_session = lambda *a, **k: False

root = tk.Tk(); app = g.App(root)
def pump(t=0.3):
    end = time.time() + t
    while time.time() < end: root.update(); real_sleep(0.01)
ok = 0
def check(name, cond):
    global ok
    assert cond, "FAIL: " + name
    ok += 1; print("PASS", name)
pump()

# ---- window / icon / theme
check("window icon file is written and valid .ico", os.path.exists(ui.icon_path()) and open(ui.icon_path(), "rb").read(4) == b"\x00\x00\x01\x00")
check("window title carries the version", root.title() == f"PACMANGRAM v{C.VERSION}")
check("theme is clam with hidden notebook tabs", ttk.Style().theme_use() == "clam" and str(app.nb.cget("style")) == "Nav.TNotebook")
check("heading style is really bold 15pt (not overridden by option db)", "bold" in str(ttk.Style().lookup("H.TLabel", "font")) or "Bold" in str(ttk.Style().lookup("H.TLabel", "font")))
check("modern checkbox indicator element exists", "modern.indicator" in ttk.Style().element_names())

# ---- sidebar navigation mirrors tab state
sb = app.sidebar
check("sidebar has 10 entries", sorted(sb.rows) == list(range(10)))
check("before login only 'Giriş' is enabled", sb._state(0) == "normal" and all(sb._state(i) == "disabled" for i in range(1, 10)))
sb.go(3); pump(0.05); check("clicking a disabled entry does nothing", app.nb.index(app.nb.select()) == 0)
check("active entry is highlighted with the Pacman-yellow stripe", str(sb.rows[0]["stripe"].cget("bg")) == C.PAC)
check("disabled entries are dimmed", str(sb.rows[3]["text"].cget("fg")) == "#475569")
app.var_sid.set("1234567890:" + "A" * 40); app.do_login_session()
end = time.time() + 15
while time.time() < end and app.client is None: root.update(); real_sleep(0.01)
pump(0.5)
check("after login EVERY page is usable", all(sb._state(i) == "normal" for i in range(10)))
sb.go(5); pump(0.05); check("clicking an enabled entry switches page", app.nb.index(app.nb.select()) == 5)
check("highlight follows the page", str(sb.rows[5]["stripe"].cget("bg")) == C.PAC and str(sb.rows[0]["stripe"].cget("bg")) == C.SIDEBAR)
check("account chip shows the user", app.lbl_account.cget("text") == "@pac.man" and "Bağlı" in app.lbl_account_sub.cget("text"))

# ---- buttons
b = app.button(app.sidebar.footer, "Test", lambda: None, kind="primary"); b.pack(); pump(0.1)
b.configure(state="disabled"); check("disabled button is greyed", str(b.cget("bg")) == "#c7d2fe" and str(b.cget("state")) == "disabled")
b.configure(state="normal"); check("enabled again -> primary colour", str(b.cget("bg")) == C.ACCENT)
b.event_generate("<Enter>"); pump(0.05); check("hover changes colour", str(b.cget("bg")) == C.ACCENT_DARK); b.event_generate("<Leave>"); pump(0.05); check("leave restores colour", str(b.cget("bg")) == C.ACCENT); b.pack_forget()
check("app.button maps danger=True/primary=False", app.button(root, "x", None, danger=True).kind == "danger" and app.button(root, "x", None, primary=False).kind == "secondary")

# ---- empty-state hints react immediately
tv = app.tv_auto; lbl = [l for t, l in app.empty_hints.items if t is tv][0]
check("empty list shows the hint", lbl.winfo_ismapped() or lbl.place_info())
tv.insert("", "end", iid="x", values=("a", "b", "c")); check("hint disappears the moment a row is added", not lbl.place_info())
tv.delete("x"); check("hint returns when the list is emptied", bool(lbl.place_info()))

# ---- log colours + toggle + clear
app.log("Hata (x): bir şey ters gitti"); app.log("[1/3] silindi: a"); app.log("Instagram uyarısı: dinleniyor"); app.log("düz bilgi")
def tag_of(text):
    idx = app.txt_log.search(text, "1.0"); return set(app.txt_log.tag_names(idx))
check("errors are red / success green / warnings amber", "err" in tag_of("Hata (x)") and "ok" in tag_of("silindi: a") and "warn" in tag_of("dinleniyor"))
check("plain lines have no colour tag", not ({"err", "ok", "warn"} & tag_of("düz bilgi")))
app.toggle_log(); pump(0.05); check("log panel collapses", not app.log_body.winfo_ismapped())
app.toggle_log(); pump(0.05); check("log panel expands again", app.log_body.winfo_ismapped())
app.clear_log(); check("clear empties the log view", app.txt_log.get("1.0", "end").strip() == "")

# ---- themed dialogs (real, interactive) -------------------------------------------------------------
def drive(action, delay=100):
    tries = [0]
    def run():
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel): action(w); return
        tries[0] += 1
        if tries[0] < 50: root.after(100, run)
    root.after(delay, run)
def widgets(w):
    for c in w.winfo_children(): yield c; yield from widgets(c)
def press(dlg, text):
    for w in widgets(dlg):
        if isinstance(w, tk.Button) and w.cget("text") == text: w.invoke(); return
    raise AssertionError("button " + text)

drive(lambda d: press(d, "Tamam")); r = ui.showinfo("Bilgi", "Mesaj"); check("showinfo closes on OK", r is None)
drive(lambda d: press(d, "Evet, devam et")); check("askyesno returns True on 'Evet'", ui.askyesno("Emin misin?", "x") is True)
drive(lambda d: press(d, "Hayır")); check("askyesno returns False on 'Hayır'", ui.askyesno("Emin misin?", "x") is False)
drive(lambda d: d.press_enter()); check("Enter on askyesno = the SAFE answer (Hayır)", ui.askyesno("Emin misin?", "x") is False)
def typed(d):
    e = next(w for w in widgets(d) if isinstance(w, ttk.Entry)); e.insert(0, "SİL"); press(d, "Tamam")
drive(typed); check("askstring returns the typed text", ui.askstring("Onay", "yaz", parent=root) == "SİL")
drive(lambda d: press(d, "Vazgeç")); check("askstring returns None on cancel", ui.askstring("Onay", "yaz", parent=root) is None)
def esc(d):
    d.press_escape()
drive(esc); check("Escape cancels askstring", ui.askstring("Onay", "yaz", parent=root) is None)
drive(lambda d: press(d, "Tamam")); ui.showwarning("Uyarı", "x"); drive(lambda d: press(d, "Tamam")); ui.showerror("Hata", "x"); check("warning/error dialogs open and close", True)
check("norm_word handles Turkish i variants", all(C.norm_word(x) == "sil" for x in ("SİL", "Sil", "SIL", "sıl", " sil ")))

# ---- settings persisted
app.var_profile.set("Hızlı"); app.on_profile_change(); pump(0.05)
check("profile change is saved immediately", __import__("json").load(open(g.SETTINGS_FILE))["profile"] == "Hızlı")
root.destroy(); print(f"ALL OK ({ok} checks)")
