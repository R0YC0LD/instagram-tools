"""Chat backup (TXT + images), saved-posts cleaner and the account page - all against a fake client."""
import os, sys, time, types, tempfile, shutil
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import tkinter as tk
import igdm_app as g
import igdm_extra as X
import igdm_core

D = tempfile.mkdtemp()
BK = os.path.join(D, "backups")
g.SETTINGS_FILE = os.path.join(D, "s.json"); g.PROTECTED_FILE = os.path.join(D, "p.json"); g.LOG_FILE = os.path.join(D, "l.log"); g.KEEP_FILE = os.path.join(D, "k.json")
for p in g.PROFILES.values(): p.update(unsend=(0, 0), hide=(0, 0), story=(0, 0), unblock=(0, 0), unlike=(0, 0), unsave=(0, 0), download=(0, 0), rest=(0, 0), batch=10**6)
g.SOFT_PAUSE = (0, 0); g.NET_BACKOFF = (0, 0, 0, 0)
real_sleep = time.sleep; g.time.sleep = lambda s: real_sleep(0.0005)
n_ok = 0
def check(name, cond, detail=""):
    global n_ok
    assert cond, "FAIL: " + name + (f"  -> {detail}" if detail else "")
    n_ok += 1; print("PASS", name)

# ------------------------------------------------------------------------------------ pure helpers
check("safe_name strips Windows-illegal characters", X.safe_name('a/b:c*d?"e<f>g|h') == "a_b_c_d__e_f_g_h")
check("safe_name handles reserved names, trailing dots/spaces and emptiness", X.safe_name("CON") == "_CON" and X.safe_name("  abc. . ") == "abc" and X.safe_name("...") == "sohbet")
check("safe_name keeps Turkish letters and limits the length", X.safe_name("Çağrı Şükrü İğdır") == "Çağrı Şükrü İğdır" and len(X.safe_name("x" * 500)) == 80)
check("file_ext uses the URL extension, else a sensible default", X.file_ext("https://a.cdninstagram.com/x/y.webp?stp=1", "image") == ".webp" and X.file_ext("https://a.fbcdn.net/x/audio", "voice") == ".m4a" and X.file_ext("https://a/x.php", "image") == ".jpg")
photo = {"item_id": "1", "item_type": "media", "media": {"image_versions2": {"candidates": [{"url": "https://scontent.cdninstagram.com/a/big.jpg"}, {"url": "https://scontent.cdninstagram.com/a/small.jpg"}]}}}
video = {"item_id": "2", "item_type": "media", "media": {"video_versions": [{"url": "https://scontent.cdninstagram.com/v/clip.mp4"}], "image_versions2": {"candidates": [{"url": "https://scontent.cdninstagram.com/v/thumb.jpg"}]}}}
voice = {"item_id": "3", "item_type": "voice_media", "voice_media": {"media": {"audio": {"audio_src": "https://scontent.cdninstagram.com/a/v.m4a"}}}}
check("media_refs: photo -> best image; video -> video only (no thumbnail); voice -> audio", X.media_refs(photo) == [("image", "https://scontent.cdninstagram.com/a/big.jpg")] and X.media_refs(video) == [("video", "https://scontent.cdninstagram.com/v/clip.mp4")] and X.media_refs(voice) == [("voice", "https://scontent.cdninstagram.com/a/v.m4a")] and X.media_refs({"item_type": "text"}) == [])
check("account: join-date parsing (English/Turkish month names)", X.parse_join_date("September 2019") == (2019, 9) and X.parse_join_date("Eylül 2019") == (2019, 9) and X.parse_join_date("Joined March 3, 2020") == (2020, 3) and X.parse_join_date("") is None)
from datetime import datetime
check("account: age from the join month", X.account_age((2019, 9), datetime(2026, 9, 20)) == (7, 0) and X.account_age((2024, 11), datetime(2026, 2, 1)) == (1, 3))
check("mask hides the middle of e-mails and phones", X.mask("onur.t@example.com") == "on••••@example.com" and X.mask("+905551234567").startswith("+9") and "•" in X.mask("+905551234567") and X.mask(None) == "")
try:
    X.fetch_to_file("https://evil.example.com/x.jpg", os.path.join(D, "x.jpg")); blocked = False
except igdm_core.BlockedDestination:
    blocked = True
check("the real downloader is stopped by the network guard for non-Instagram hosts", blocked)

# ------------------------------------------------------------------------------------ fake Instagram
def ts(minutes): return int((datetime(2026, 3, 1, 12, 0, 0).timestamp() + minutes * 60) * 1_000_000)
def msgs_for(tid, other_pk, n_extra=0):
    base = [
        {"item_id": f"{tid}-1", "user_id": other_pk, "item_type": "text", "text": "Selam!\nNasılsın?", "timestamp": ts(1)},
        {"item_id": f"{tid}-2", "user_id": 7, "item_type": "text", "text": "İyiyim, sen?", "timestamp": ts(2), "reactions": {"emojis": [{"emoji": "❤"}]}},
        {"item_id": f"{tid}-3", "user_id": other_pk, "item_type": "media", "timestamp": ts(3), "media": {"image_versions2": {"candidates": [{"url": f"https://scontent.cdninstagram.com/{tid}/one.jpg"}]}}},
        {"item_id": f"{tid}-4", "user_id": 7, "item_type": "media", "timestamp": ts(4), "media": {"image_versions2": {"candidates": [{"url": f"https://scontent.cdninstagram.com/{tid}/two.jpg"}]}}},
        {"item_id": f"{tid}-5", "user_id": other_pk, "item_type": "voice_media", "timestamp": ts(5), "voice_media": {"media": {"audio": {"audio_src": f"https://scontent.cdninstagram.com/{tid}/v.m4a"}}}},
        {"item_id": f"{tid}-6", "user_id": other_pk, "item_type": "media", "timestamp": ts(6), "media": {"video_versions": [{"url": f"https://scontent.cdninstagram.com/{tid}/c.mp4"}]}},
        {"item_id": f"{tid}-7", "user_id": 7, "item_type": "like", "timestamp": ts(7)},
        {"item_id": f"{tid}-8", "user_id": other_pk, "item_type": "action_log", "timestamp": ts(8), "action_log": {"description": "ali bir mesajı beğendi"}},
    ]
    return base
THREADS = [
    {"thread_id": "100", "thread_title": "", "users": [{"pk": 9, "username": "ayse.yilmaz"}], "last_activity_at": ts(100), "items": []},
    {"thread_id": "200", "thread_title": "Hafta sonu / grup: 2026", "users": [{"pk": 8, "username": "ali"}, {"pk": 6, "username": "veli"}], "last_activity_at": ts(90), "items": []},
    {"thread_id": "300", "thread_title": "", "users": [{"pk": 5, "username": "ayse.yilmaz"}], "last_activity_at": ts(80), "items": []},   # same name, different person
    {"thread_id": "400", "thread_title": "", "users": [{"pk": 4, "username": "con"}], "last_activity_at": ts(70), "items": []},         # reserved Windows name
]
OTHER = {"100": 9, "200": 8, "300": 5, "400": 4}
calls = {"threads": 0, "inbox": 0}
SAVED = [{"media": {"id": f"{6000 + i}_9", "media_type": 8 if i % 3 == 0 else 1, "taken_at": 1700000000 + i, "user": {"username": f"kaydeden{i}"}, "caption": {"text": f"kayıt {i}"}}} for i in range(30)]
unsaved = []

class FakeClient:
    uuid = "u"; token = "t"; user_id = "7"
    about_error = False
    def __init__(self): self.challenge_code_handler = self.change_password_handler = None
    def login_by_sessionid(self, sid): pass
    def account_info(self): return types.SimpleNamespace(pk="7", username="onur.test", full_name="Onur Test", is_private=False, is_verified=True, biography="Merhaba dünya", external_url="https://example.com", is_business=False, email="onur.test@example.com", phone_number="+905551234567", birthday=None, gender=None)
    def user_info(self, uid): return types.SimpleNamespace(username="onur.test", full_name="Onur Test", media_count=1234, follower_count=56789, following_count=321)
    def user_about_v1(self, uid):
        if FakeClient.about_error: raise RuntimeError("bloks failed")
        return types.SimpleNamespace(date="September 2019", country="Turkey", former_usernames="onur_old")
    def media_unsave(self, mid): unsaved.append(str(mid)); return True
    def private_request(self, ep, params=None, data=None, with_signature=True):
        params = params or {}
        if ep == "direct_v2/inbox/":
            calls["inbox"] += 1; return {"inbox": {"threads": THREADS, "has_older": False}}
        if ep.startswith("direct_v2/threads/") and ep.endswith("/"):
            tid = ep.split("/")[2]; calls["threads"] += 1
            allm = msgs_for(tid, OTHER[tid]); allm.sort(key=lambda m: -int(m["timestamp"]))     # newest first, like Instagram
            start = int(params.get("cursor") or 0); page = allm[start:start + 5]
            th = next(t for t in THREADS if t["thread_id"] == tid)
            return {"thread": {"users": th["users"], "items": page, "has_older": start + 5 < len(allm), "oldest_cursor": str(start + 5)}}
        if ep == "feed/saved/posts/":
            s = int(params.get("max_id") or 0); return {"items": SAVED[s:s + 12], "next_max_id": str(s + 12) if s + 12 < len(SAVED) else ""}
        raise AssertionError(ep)
g.Client = FakeClient; g.load_session = lambda *a, **k: False
infos = []; g.ui.showinfo = lambda *a, **k: infos.append(a[1] if len(a) > 1 else ""); g.ui.showwarning = lambda *a, **k: infos.append("WARN " + str(a[1:])); g.ui.askstring = lambda *a, **k: "KALDIR"

downloads = []; fail_urls = set()
def fake_fetch(url, path, timeout=None):
    downloads.append(url)
    if url in fail_urls: raise ConnectionError("simulated drop")
    with open(path, "wb") as fp: fp.write(b"BIN:" + url.encode())
X.fetch_to_file = fake_fetch

root = tk.Tk(); app = g.App(root)
def pump(cond=lambda: True, t=30):
    end = time.time() + t
    while time.time() < end:
        root.update()
        if cond(): return True
        real_sleep(0.005)
    return cond()
app.var_sid.set("1234567890:" + "A" * 40); app.do_login_session(); pump(lambda: app.client is not None); pump(lambda: not app.busy)
saved_tab, backup, account = app.bulk_tabs[3], app.bulk_tabs[4], app.bulk_tabs[5]
check("all 10 pages are enabled after login", all(str(app.nb.tab(i, "state")) == "normal" for i in range(10)) and app.nb.index("end") == 10)

# ------------------------------------------------------------------------------------ saved posts
saved_tab.scan(); check("saved: 30 saved posts scanned over 3 pages", pump(lambda: not app.busy and len(saved_tab.items) == 30))
saved_tab.toggle_protect("6004_9")
saved_tab.start(); infos.clear(); pump(lambda: not app.busy and infos)
check("saved: unsaved 29 posts one by one, kept the protected one", len(unsaved) == 29 and "6004_9" not in unsaved and len(set(unsaved)) == 29)

# ------------------------------------------------------------------------------------ backup
backup.var_dir.set(BK); backup.var_img.set(True); backup.var_vid.set(False); backup.var_voice.set(False)
backup.load_chats(); check("backup: 4 chats listed (newest first)", pump(lambda: not app.busy and len(backup.threads) == 4) and list(backup.tv.get_children()) == ["100", "200", "300", "400"])
check("backup: nothing selected -> friendly hint, nothing runs", (backup.start(), infos[-1])[1].startswith("Önce yedeklenecek") and not app.busy)
backup.tv.selection_set(["100", "200", "300", "400"]); fail_urls.add("https://scontent.cdninstagram.com/200/two.jpg")
infos.clear(); backup.start(); check("backup run finished", pump(lambda: not app.busy and infos, 60))
folders = sorted(os.listdir(BK))
check("backup: one folder per person, unsafe names sanitised, name clash / reserved name handled", set(folders) == {"_con", "ayse.yilmaz", "ayse.yilmaz (2)", "Hafta sonu _ grup_ 2026"}, folders)
f100 = os.path.join(BK, "ayse.yilmaz")
txt = open(os.path.join(f100, "sohbet.txt"), encoding="utf-8-sig").read()
check("backup: sohbet.txt is UTF-8 with BOM and CRLF (opens correctly in Notepad)", open(os.path.join(f100, "sohbet.txt"), "rb").read(3) == b"\xef\xbb\xbf" and "\r\n" in open(os.path.join(f100, "sohbet.txt"), "rb").read().decode("utf-8-sig"))
lines = [l for l in txt.replace("\r", "").split("\n") if l.startswith("[2026")]
check("backup: messages are in chronological order with timestamps and sender names", [l[1:20] for l in lines] == sorted(l[1:20] for l in lines) and lines[0].endswith("ayse.yilmaz: Selam!") and "] Ben: İyiyim, sen?" in txt)
check("backup: multi-line messages keep their second line, reactions are noted", "Nasılsın?" in txt and "tepkiler: ❤" in txt)
imgs = sorted(os.listdir(os.path.join(f100, "gorseller")))
check("backup: photos downloaded into gorseller/ with ordered, sender-tagged names", len(imgs) == 2 and imgs[0].startswith("00003_20260301-120300_ayse.yilmaz") and imgs[1].startswith("00004_") and "_ben" in imgs[1])
check("backup: text refers to the saved file; videos/voice are NOT downloaded by default", "[Fotoğraf: gorseller/00003_" in txt and "[Video]" in txt and "[Sesli mesaj]" in txt and not os.path.exists(os.path.join(f100, "videolar")) and not os.path.exists(os.path.join(f100, "sesli_mesajlar")))
check("backup: system / like messages keep readable placeholders", "[Sistem] ali bir mesajı beğendi" in open(os.path.join(BK, "Hafta sonu _ grup_ 2026", "sohbet.txt"), encoding="utf-8-sig").read() and "[Beğeni]" in txt)
t200 = open(os.path.join(BK, "Hafta sonu _ grup_ 2026", "sohbet.txt"), encoding="utf-8-sig").read()
check("backup: a failed download is counted, noted as [Fotoğraf] without a file, and the chat still completes", "two.jpg" not in " ".join(os.listdir(os.path.join(BK, "Hafta sonu _ grup_ 2026", "gorseller"))) and "Ben: [Fotoğraf]" in t200 and "indirilemedi" in backup.tv.set("200", "status"))
check("backup: row status shows message and file counts", "Tamam" in backup.tv.set("100", "status") and "8 mesaj, 2 dosya" in backup.tv.set("100", "status"))
check("backup: every chat has its .thread_id marker; no .part/.tmp leftovers", all(os.path.exists(os.path.join(BK, f, ".thread_id")) for f in folders) and not [p for r, _, fs in os.walk(BK) for p in fs if p.endswith((".part", ".tmp"))])
check("backup: settings (folder + options) are saved", __import__("json").load(open(g.SETTINGS_FILE)).get("backup_dir") == BK)

# re-run: existing files are not downloaded again
fail_urls.clear(); downloads.clear(); infos.clear(); backup.tv.selection_set(["100"]); backup.start(); pump(lambda: not app.busy and infos)
check("backup: running again downloads nothing that already exists", downloads == [])
# options: videos + voice
downloads.clear(); infos.clear(); backup.var_vid.set(True); backup.var_voice.set(True); backup.tv.selection_set(["100"]); backup.start(); pump(lambda: not app.busy and infos)
check("backup: with video/voice options on, exactly those extra files are fetched", sorted(x.split("/")[-1] for x in downloads) == ["c.mp4", "v.m4a"] and os.path.exists(os.path.join(f100, "videolar")) and os.path.exists(os.path.join(f100, "sesli_mesajlar")))
# images off
shutil.rmtree(os.path.join(BK, "ayse.yilmaz (2)")); downloads.clear(); infos.clear(); backup.var_img.set(False); backup.var_vid.set(False); backup.var_voice.set(False); backup.tv.selection_set(["300"]); backup.start(); pump(lambda: not app.busy and infos)
check("backup: with images off only the text is written", downloads == [] and os.path.exists(os.path.join(BK, "ayse.yilmaz (2)", "sohbet.txt")) and not os.path.exists(os.path.join(BK, "ayse.yilmaz (2)", "gorseller")))
# stop in the middle
backup.var_img.set(True); shutil.rmtree(os.path.join(BK, "_con")); infos.clear(); backup.tv.selection_set(["100", "200", "300", "400"])
orig_fetch = X.fetch_to_file
def stopper(url, path, timeout=None):
    orig_fetch(url, path); app.stop_event.set()
X.fetch_to_file = stopper; backup.start(); pump(lambda: not app.busy and infos, 60); X.fetch_to_file = orig_fetch
check("backup: Stop ends the run cleanly and unlocks the UI", not app.busy and "durduruldu" in backup.lbl_status.cget("text").lower())
app.stop_event.clear()

# ------------------------------------------------------------------------------------ account page
app.nb.select(9); check("account: page loads by itself the first time it is opened", pump(lambda: account.loaded and not app.busy))
v = {k: lbl.cget("text") for k, lbl in account.rows.items()}
check("account: name, id, counts, type, bio, link", v["username"] == "onur.test" and v["full_name"] == "Onur Test" and v["pk"] == "7" and v["posts"] == "1.234" and v["followers"] == "56.789" and v["following"] == "321" and "Doğrulanmış" in v["kind"] and "Herkese açık" in v["kind"] and v["bio"] == "Merhaba dünya" and v["link"] == "https://example.com")
age_y = datetime.now().year - 2019 - (1 if datetime.now().month < 9 else 0)
check("account: creation date, country, previous usernames and computed account age", v["created"] == "September 2019" and v["country"] == "Turkey" and v["former"] == "onur_old" and v["age"].startswith(f"{age_y} yıl"))
check("account: e-mail and phone are masked on screen", "•" in v["email"] and "onur.test@" not in v["email"] and "•" in v["phone"] and "5551234" not in v["phone"])
check("account: header shows the name and @handle", account.lbl_name.cget("text") == "Onur Test" and account.lbl_handle.cget("text") == "@onur.test")
FakeClient.about_error = True; account.refresh(); pump(lambda: not app.busy)
v = {k: lbl.cget("text") for k, lbl in account.rows.items()}
check("account: if Instagram refuses the 'about' data the rest still shows, with an explanation", v["username"] == "onur.test" and v["followers"] == "56.789" and v["created"] == "—" and "açılış tarihi" in account.lbl_status.cget("text"))
app.logout(); check("logout clears the account page and the backup list", account.rows["username"].cget("text") == "—" and backup.threads == [] and str(app.nb.tab(8, "state")) == "disabled")
root.destroy(); print(f"ALL OK ({n_ok} checks)")
