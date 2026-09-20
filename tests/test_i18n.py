"""Languages: catalog completeness, live language switch (login + page kept), English dialogs and confirm words."""
import os, sys, re, time, types, json, tempfile
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
TOOLS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
sys.path[:0] = [SRC, TOOLS]
import tkinter as tk
from tkinter import ttk
import igdm_app as g
import igdm_i18n as I
from i18n_keys import collect, placeholders

D = tempfile.mkdtemp()
g.SETTINGS_FILE = os.path.join(D, "s.json"); g.PROTECTED_FILE = os.path.join(D, "p.json"); g.LOG_FILE = os.path.join(D, "l.log"); g.KEEP_FILE = os.path.join(D, "k.json")
for _p in g.PROFILES.values(): _p.update(unsend=(0, 0), hide=(0, 0), story=(0, 0), unblock=(0, 0), unlike=(0, 0), unsave=(0, 0), download=(0, 0), rest=(0, 0), batch=10**6)
g.SOFT_PAUSE = (0, 0); g.LONG_REST = (0, 0)
real_sleep = time.sleep; g.time.sleep = lambda s: real_sleep(0.002)
n_ok = 0
def check(name, cond, detail=""):
    global n_ok
    assert cond, "FAIL: " + name + (f"  -> {detail}" if detail else "")
    n_ok += 1; print("PASS", name)

# ------------------------------------------------------------------ catalogs
keys = [k for k, _ in collect()]
check("the source has translatable strings", len(keys) > 300, len(keys))
for code in I.CODES:
    if code == "tr":
        continue
    cat = I.catalog(code)
    miss = [k for k in keys if k not in cat]
    check(f"catalog '{code}' translates every string", not miss, miss[:5])
    extra = [k for k in cat if k not in keys]
    check(f"catalog '{code}' has no stale entries", not extra, extra[:5])
    bad = [k for k in keys if placeholders(k) != placeholders(cat[k])]
    check(f"catalog '{code}' keeps every {{n}} placeholder", not bad, bad[:3])
    empty = [k for k in keys if not str(cat[k]).strip()]
    check(f"catalog '{code}' has no empty translation", not empty, empty[:3])
check("app names exist for every language", all(c in I.APP_NAMES for c in I.CODES))
check("tr() fills placeholders and remembers the Turkish source", I.tr("{0} sohbet bulundu.", 3) == "3 sohbet bulundu." and I.tr("{0} sohbet bulundu.", 3).src == "3 sohbet bulundu.")
I.set_language("en")
check("tr() in English", I.tr("{0} sohbet bulundu.", 3) == "3 chats found." and I.app_title() == "Instagram Tools")
check("a broken placeholder never crashes tr()", str(I.tr("Yok {9}", 1)) == "Yok {9}")
I.set_language("tr"); I._missing.clear()

# ------------------------------------------------------------------ fake client
BLOCKED = [{"user_id": 1000 + i, "username": f"blk{i}", "full_name": f"Kişi {i}", "block_at": 1700000000 + i} for i in range(6)]
calls = []
class FakeClient:
    uuid = "u"; token = "t"; user_id = "7"
    def __init__(self): self.challenge_code_handler = None; self.change_password_handler = None
    def login_by_sessionid(self, sid): pass
    def account_info(self): return types.SimpleNamespace(username="me", pk=7)
    def user_unblock(self, uid): calls.append(str(uid)); return True
    def private_request(self, ep, params=None, data=None, with_signature=True):
        if ep == "direct_v2/inbox/": return {"inbox": {"threads": [], "has_older": False}}
        if ep == "users/blocked_list/": return {"blocked_list": BLOCKED, "next_max_id": "", "page_size": 20}
        raise AssertionError(ep)
g.Client = FakeClient; g.load_session = lambda *a, **k: False
infos = []; g.ui.showinfo = lambda *a, **k: infos.append(a[1] if len(a) > 1 else "")
g.ui.showwarning = lambda *a, **k: None
asked = []; typed = {"v": "KALDIR"}
g.ui.askstring = lambda title, prompt, **k: (asked.append(str(prompt)), typed["v"])[1]

root = tk.Tk(); app = g.App(root)
def pump(cond, t=30):
    end = time.time() + t
    while time.time() < end:
        root.update()
        if cond(): return True
        real_sleep(0.01)
    raise TimeoutError
def settle(t=0.2):
    end = time.time() + t
    while time.time() < end: root.update(); real_sleep(0.01)

check("starts in Turkish by default", I.get_language() == "tr" and root.title().startswith("Instagram Araçları"))
app.var_sid.set("1234567890:" + "A" * 40); app.do_login_session(); pump(lambda: app.client is not None); pump(lambda: not app.busy)
client = app.client
app.nb.select(5); settle()

# ------------------------------------------------------------------ live switch to English
check("language switch is refused while a task runs", (setattr(app, "busy", True), app.change_language("en"))[1] is False and I.get_language() == "tr")
app.busy = False; infos.clear()
check("change to the same language does nothing", app.change_language("tr") is False)
app.cmb_lang.set("English"); app.var_lang_disp.set("English"); app.cmb_lang.event_generate("<<ComboboxSelected>>"); settle(0.5)
check("choosing English in the sidebar switches the language", I.get_language() == "en")
check("window title is English", root.title().startswith("Instagram Tools v"), root.title())
check("login survives the rebuild (same client, no new login)", app.client is client and app.my_username == "me")
check("the page you were on is still open", app.nb.index(app.nb.select()) == 5)
sb = app.sidebar
labels = [str(sb.rows[i]["text"].cget("text")) for i in sorted(sb.rows)]
check("sidebar entries are English", labels[0] == "Login" and "DM cleanup" in labels and "Blocks" in labels and "Saved" in labels, labels)
check("every page is still usable after the rebuild", all(sb._state(i) == "normal" for i in range(10)))
check("account chip is English", "Connected" in app.lbl_account_sub.cget("text") and app.lbl_account.cget("text") == "@me")
check("language is saved in the settings", json.load(open(g.SETTINGS_FILE, encoding="utf-8")).get("language") == "en")
check("speed profile names are translated", list(app.cmb_profile.cget("values")) == ["Safe", "Balanced", "Fast"], app.cmb_profile.cget("values"))
app.var_profile_disp.set("Fast"); app.cmb_profile.event_generate("<<ComboboxSelected>>"); settle()
check("picking a translated profile stores the Turkish id", app.var_profile.get() == "Hızlı" and g.profile_id("Fast") == "Hızlı")
app.var_profile_disp.set("Balanced"); app.cmb_profile.event_generate("<<ComboboxSelected>>"); settle()
check("profile is remembered across a second switch", json.load(open(g.SETTINGS_FILE, encoding="utf-8")).get("profile") == "Dengeli")

# ------------------------------------------------------------------ English flow: blocked tab
blocked = app.bulk_tabs[1]
blocked.scan(); pump(lambda: not app.busy and blocked.items)
check("scan works in English", len(blocked.items) == 6)
headings = [str(blocked.tv.heading(c, "text")) for c in blocked.tv["columns"]]
check("table headings are English", "Name" in headings and "Blocked on" in headings and "Status" in headings, headings)
blocked.toggle_protect("1003")
check("protected rows read 'Protected ★'", blocked.tv.set("1003", "status") == "Protected ★", blocked.tv.set("1003", "status"))
typed["v"] = "REMOVE"; calls.clear(); asked.clear(); infos.clear()
blocked.start(); pump(lambda: not app.busy and infos)
check("English confirm word REMOVE is accepted and asked for", asked and "REMOVE" in asked[0] and len(calls) == 5 and "1003" not in calls, (asked[:1], calls))
check("English confirmation text is fully English", not re.search(r"[ğışĞİ]", asked[0]), asked[0][:200])

# ------------------------------------------------------------------ Turkish word still accepted
BLOCKED[:] = [{"user_id": 2000 + i, "username": f"x{i}", "full_name": f"K {i}", "block_at": 1700000000 + i} for i in range(3)]
blocked.scan(); pump(lambda: not app.busy and blocked.items)
typed["v"] = "yanlis"; calls.clear(); infos.clear(); blocked.start(); settle(0.2)
check("a wrong word does nothing", not calls and not app.busy)
typed["v"] = "kaldır"; calls.clear(); infos.clear(); blocked.start(); pump(lambda: not app.busy and infos)
check("the Turkish word is accepted in English mode too", len(calls) == 3, calls)

# ------------------------------------------------------------------ auto DM cleanup confirm word
check("auto-cleanup confirm word translates", I.tr("SİL") == "DELETE")

# ------------------------------------------------------------------ nothing left untranslated on screen
ALLOWED = ("Türkçe", "Türkiye", "Teryakioğlu", "Kişi", "K ")
TR_CHARS = re.compile(r"[ğışĞİŞçÇöÖüÜ]")
def texts(widget):
    out = []
    for w in widget.winfo_children():
        try: out.append(str(w.cget("text")))
        except tk.TclError: pass
        if isinstance(w, ttk.Treeview):
            for c in w["columns"]: out.append(str(w.heading(c, "text")))
        if isinstance(w, ttk.Combobox): out += [str(v) for v in w.cget("values")]
        out += texts(w)
    return out
for page in range(10):
    app.nb.select(page); settle(0.05)
left = []
for t in texts(root):
    s = t
    for a in ALLOWED: s = s.replace(a, "")
    if TR_CHARS.search(s): left.append(t[:80])
check("no Turkish text is left in the English window", not left, left[:6])
check("no string fell back to Turkish while exercising the app", not I.missing(), sorted(I.missing())[:5])

# ------------------------------------------------------------------ rebuild stress: no crash, no leak, stays fast
t0 = time.perf_counter(); lengths = []
for i in range(8):
    app.change_language("tr" if I.get_language() == "en" else "en"); settle(0.05)
    lengths.append(len(root.winfo_children()))
per = (time.perf_counter() - t0) / 8
check("8 quick language switches: window still alive, login kept", app.client is client and root.winfo_exists())
check("rebuilds do not leak widgets (top-level child count is stable)", len(set(lengths)) == 1, lengths)
check("a language switch takes well under a second", per < 1.0, f"{per:.3f}s")
check("an even number of switches ends in English again", I.get_language() == "en" and app.var_lang_disp.get() == "English")

# ------------------------------------------------------------------ back to Turkish
app.var_lang_disp.set("Türkçe"); app.cmb_lang.event_generate("<<ComboboxSelected>>"); settle(0.5)
check("switch back to Turkish", I.get_language() == "tr" and root.title().startswith("Instagram Araçları") and app.client is client)
check("Turkish sidebar is back", "Engeller" in [str(app.sidebar.rows[i]["text"].cget("text")) for i in sorted(app.sidebar.rows)])
check("settings say 'tr' again", json.load(open(g.SETTINGS_FILE, encoding="utf-8")).get("language") == "tr")
check("all pages usable after two rebuilds", all(app.sidebar._state(i) == "normal" for i in range(10)))
root.destroy()
print(f"\n{n_ok} checks passed")
