import os, sys
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import sys, time, types, json, os, tempfile
from datetime import datetime, timedelta
pass
import tkinter as tk
import igdm_app as g
import igdm_bulk as b
from instagrapi.exceptions import PleaseWaitFewMinutes, FeedbackRequired

D = tempfile.mkdtemp()
g.SETTINGS_FILE = os.path.join(D, "s.json"); g.PROTECTED_FILE = os.path.join(D, "p.json"); g.LOG_FILE = os.path.join(D, "l.log"); g.KEEP_FILE = os.path.join(D, "k.json")
for _p in g.PROFILES.values(): _p.update(unsend=(0, 0), hide=(0, 0), story=(0, 0), unblock=(0, 0), unlike=(0, 0), rest=(0, 0), batch=10**6)
g.SOFT_PAUSE = (0, 0); g.LONG_REST = (0, 0)
real_sleep = time.sleep; g.time.sleep = lambda s: real_sleep(0.002)

NOW = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
# 12 archive days: day i is i*20 days old, 3 stories each
DAYS = [types.SimpleNamespace(id=f"d{i}", timestamp=NOW - timedelta(days=20 * i), media_count=3) for i in range(1, 13)]
BLOCKED = [{"user_id": 1000 + i, "username": f"blk{i}", "full_name": f"Kişi {i}", "block_at": 1700000000 + i} for i in range(45)]
LIKED = [{"media": {"id": f"{5000 + i}_9", "pk": 5000 + i, "media_type": 8 if i % 3 == 0 else 1, "taken_at": 1700000000 + i,
                    "user": {"username": f"owner{i}"}, "caption": {"text": f"gönderi {i}"}}} if i % 2 == 0 else
         {"id": f"{5000 + i}_9", "pk": 5000 + i, "media_type": 2, "product_type": "clips", "taken_at": 1700000000 + i,
          "user": {"username": f"owner{i}"}, "caption": None} for i in range(50)]
calls = []; inject = {"exc": []}; falsy = {"story": set(), "like": set()}

def maybe_raise():
    if inject["exc"]:
        e = inject["exc"].pop(0)
        if e: raise e

class FakeClient:
    uuid = "u"; token = "t"; user_id = "7"
    def __init__(self): self.challenge_code_handler = None; self.change_password_handler = None
    def login_by_sessionid(self, sid): pass
    def account_info(self): return types.SimpleNamespace(username="me", pk=7)
    def with_default_data(self, d): return {**d, "_uuid": "u", "_uid": "7"}
    def media_id(self, pk): return f"{pk}_7"
    def _archive_story_reels(self, response): return list(response["reels"].values())
    def archive_story_days_paginated_v1(self, amount=0, end_cursor="", include_memories=True, reel_id=""):
        s = int(end_cursor or 0); page = DAYS[s:s + 5]
        return page, (str(s + 5) if s + 5 < len(DAYS) else "")
    def story_delete(self, pk):
        maybe_raise()
        if str(pk) in falsy["story"]: return False
        calls.append(("story", str(pk))); return True
    def user_unblock(self, uid):
        maybe_raise(); calls.append(("unblock", str(uid))); return True
    def media_unlike(self, mid):
        maybe_raise()
        if str(mid) in falsy["like"]: return False
        calls.append(("unlike", str(mid))); return True
    def private_request(self, ep, params=None, data=None, with_signature=True):
        if ep == "direct_v2/inbox/": return {"inbox": {"threads": [], "has_older": False}}
        if ep == "feed/reels_media_stream/":
            did = data["reel_ids"][0]
            return {"reels": {did: {"items": [{"pk": f"{did}s{k}", "id": f"{did}s{k}_7"} for k in range(3)]}}}
        if ep == "users/blocked_list/":
            s = int((params or {}).get("max_id") or 0); page = BLOCKED[s:s + 20]
            return {"blocked_list": page, "next_max_id": str(s + 20) if s + 20 < len(BLOCKED) else "", "page_size": 20}
        if ep == "feed/liked/":
            s = int((params or {}).get("max_id") or 0); page = LIKED[s:s + 18]
            return {"items": page, "next_max_id": str(s + 18) if s + 18 < len(LIKED) else ""}
        if ep.startswith("media/") and "delete" in ep:
            assert "media_type=STORY" in ep, ep
            calls.append(("story-fallback", ep.split("/")[1].split("_")[0])); return {"did_delete": True}
        raise AssertionError(ep)

g.Client = FakeClient; g.load_session = lambda *a, **k: False
infos = []; g.ui.showinfo = lambda *a, **k: infos.append(a[1] if len(a) > 1 else "")
g.ui.showwarning = lambda *a, **k: None
typed = {"v": "SİL"}; g.ui.askstring = lambda *a, **k: typed["v"]

def mk():
    root = tk.Tk(); app = g.App(root)
    def pump(cond, t=40):
        end = time.time() + t
        while time.time() < end:
            root.update()
            if cond(): return
            real_sleep(0.01)
        raise TimeoutError
    app.pump = pump
    app.var_sid.set("1234567890:" + "A" * 40); app.do_login_session(); pump(lambda: app.client is not None); pump(lambda: not app.busy)
    return root, app

def run(tab, word=None):
    if word is not None: typed["v"] = word
    infos.clear(); calls.clear()
    tab.start(); tab.app.pump(lambda: not tab.app.busy and infos)

root, app = mk()
story, blocked, likes = app.bulk_tabs
assert str(app.nb.tab(4, "state")) == "normal" and str(app.nb.tab(6, "state")) == "normal"
print("PASS after login all 3 new tabs are enabled")

# ---------------------------------------------------------------- stories
story.var_date.set((NOW - timedelta(days=100)).strftime("%d.%m.%Y")); story.scan(); app.pump(lambda: not app.busy and story.items)
assert len(story.items) == 12, len(story.items)            # 3 pages
older = [d for d in DAYS if d.timestamp.replace(hour=0) < parse if False] if False else None
cut = b.parse_date(story.var_date.get()); expect = [d.id for d in DAYS if d.timestamp < cut]
assert sorted(it["id"] for it in story.todo) == sorted(expect) and expect, (expect, [it["id"] for it in story.todo])
print("PASS story archive scanned over 3 pages; %d days older than the chosen date are planned (of 12)" % len(expect))
story.var_date.set("31.02.2025"); story.render(); assert story.todo == [] and "geçersiz" in story.lbl_status.cget("text")
story.var_date.set((NOW - timedelta(days=100)).strftime("%d.%m.%Y")); story.render()
prot = expect[0]; story.toggle_protect(prot); assert prot not in [it["id"] for it in story.todo] and story.tv.set(prot, "status") == "Korumalı ★"
print("PASS invalid date rejected; double-click protects a day")
typed["v"] = "yanlış"; calls.clear(); story.start(); root.update(); assert not calls and not app.busy; print("PASS wrong confirmation word deletes nothing")
falsy["story"] = {f"{expect[1]}s0"}          # library call returns False for one story -> raw fallback must be used
run(story, "SİL")
deleted = [c for c in calls if c[0] in ("story", "story-fallback")]
assert len(deleted) == (len(expect) - 1) * 3 and any(c[0] == "story-fallback" for c in deleted), (len(deleted), calls[:5])
assert not any(c[1].startswith(prot) for c in deleted)
assert all(d.startswith("d") for d in [c[1] for c in deleted])
print("PASS deleted every story of the planned days (%d) except the protected day; fallback endpoint used when library returned False" % len(deleted))
assert int(story.pb.cget("value")) == int(story.pb.cget("maximum")), (story.pb.cget("value"), story.pb.cget("maximum"))
falsy["story"] = set()

# ---------------------------------------------------------------- blocked
blocked.scan(); app.pump(lambda: not app.busy and blocked.items); assert len(blocked.items) == 45
blocked.toggle_protect("1003"); blocked.toggle_protect("1010")
assert json.load(open(g.KEEP_FILE))["7"]["blocked"] == ["1003", "1010"]
print("PASS 45 blocked accounts scanned over 3 pages; 2 marked 'engelli kalsın' and saved to disk")
run(blocked, "kaldır")     # lower-case + Turkish dotless i variants of KALDIR must work
ub = [c[1] for c in calls if c[0] == "unblock"]
assert len(ub) == 43 and "1003" not in ub and "1010" not in ub, len(ub)
print("PASS unblocked 43 accounts one by one, kept the 2 protected ones blocked")
assert len(blocked.items) == 2

# ---------------------------------------------------------------- likes
likes.scan(); app.pump(lambda: not app.busy and likes.items); assert len(likes.items) == 50
assert {it["cols"][1] for it in likes.items} == {"Albüm", "Fotoğraf", "Reel"}, {it["cols"][1] for it in likes.items}
likes.toggle_protect("5004_9"); falsy["like"] = {"5007_9"}
run(likes, "KALDIR")
ul = [c[1] for c in calls if c[0] == "unlike"]
assert len(ul) == 48 and "5004_9" not in ul and "5007_9" not in ul
assert sorted(it["id"] for it in likes.items) == ["5004_9", "5007_9"]
print("PASS 50 likes scanned (post/album/reel); unliked 48, skipped the protected one, the failed one stays in the list")
root.destroy()

# ------------------------------------------ warnings: soft recover, autonomous long rest, hard stop
falsy["like"] = set()
def fresh(auto_resume=True):
    root, app = mk(); app.var_autoresume.set(auto_resume)
    lk = app.bulk_tabs[2]; lk.scan(); app.pump(lambda: not app.busy and lk.items); return root, app, lk

root, app, lk = fresh()
inject["exc"] = [PleaseWaitFewMinutes("Please wait")]
run(lk, "KALDIR"); assert len([c for c in calls if c[0] == "unlike"]) == 50 and app.soft_hits == 1
print("PASS one soft warning: rested, slowed down, finished all 50")
root.destroy()

root, app, lk = fresh(True)
inject["exc"] = [PleaseWaitFewMinutes("wait")] * 5      # 3 warnings in a row -> autonomous long rest, then it carries on
run(lk, "KALDIR"); assert len([c for c in calls if c[0] == "unlike"]) == 50 and app.long_rests == 1, (app.long_rests, len(calls))
assert "Uzun mola" in app.txt_log.get("1.0", "end")
print("PASS repeated soft warnings + autonomous mode: took a long rest and completed all 50 by itself")
root.destroy()

root, app, lk = fresh(False)
inject["exc"] = [PleaseWaitFewMinutes("wait")] * 5
run(lk, "KALDIR"); assert len([c for c in calls if c[0] == "unlike"]) == 0 and "DURDURULDU" in app.txt_log.get("1.0", "end")
print("PASS same warnings with autonomous mode OFF: stopped, nothing more sent")
root.destroy()

root, app, lk = fresh(True)
inject["exc"] = [None, None, FeedbackRequired("feedback_required")]
run(lk, "KALDIR"); n = len([c for c in calls if c[0] == "unlike"])
assert n == 2 and app.long_rests == 0, n
print("PASS hard warning (feedback_required): stopped immediately after 2 unlikes, no long-rest retry")
# logout resets tabs
app.protected = set(); app.busy = False
app.logout(); assert lk.items == [] and str(app.nb.tab(6, "state")) == "disabled"
print("PASS logout clears and disables the new tabs")
root.destroy(); print("ALL OK")


