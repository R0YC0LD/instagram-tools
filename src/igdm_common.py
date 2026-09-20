"""
igdm_common.py
Shared building blocks for the Instagram cleaner: pacing, warning classification,
friendly error texts and small JSON helpers. No GUI code here.
"""

import os
import json
import random

from igdm_core import BlockedDestination, APP_DIR
from instagrapi.exceptions import (BadPassword, ChallengeRequired, PleaseWaitFewMinutes, RateLimitError,
                                   FeedbackRequired, ClientThrottledError, LoginRequired)

from igdm_meta import APP_TITLE, VERSION  # noqa: E402  (single source of truth, light-weight module)

# ---- design tokens (used by igdm_ui and the tabs) ---------------------------------------------
ACCENT = "#6366f1"          # indigo: primary actions
ACCENT_DARK = "#4f46e5"     # hover
DANGER = "#dc2626"
DANGER_DARK = "#b91c1c"
SUCCESS = "#16a34a"
WARN = "#d97706"
PAC = "#facc15"             # Pacman yellow: highlights in the sidebar
BG = "#f3f4f6"              # page background
CARD = "#ffffff"
BORDER = "#e5e7eb"
TEXT = "#111827"
MUTED = "#6b7280"
SIDEBAR = "#0f172a"
SIDEBAR_HOVER = "#1e293b"
SIDEBAR_TEXT = "#cbd5e1"
FONT = "Segoe UI"
FONT_BOLD = "Segoe UI Semibold"

SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
PROTECTED_FILE = os.path.join(APP_DIR, "protected.json")   # chats the user marked "do not delete"
KEEP_FILE = os.path.join(APP_DIR, "keep.json")             # per account: people to keep blocked, etc.
LOG_FILE = os.path.join(APP_DIR, "igdmtool.log")

# ---- pacing -----------------------------------------------------------------------------------
# (min, max) seconds between two actions, chosen at random. Every `batch` actions (+-30%) the app also
# takes a longer rest, like a person would. "unsend" = one message, "hide" = one whole conversation.
# Other kinds: "story" = delete one archived story, "unblock" = unblock one person (friendship actions are
# rate-limited harder by Instagram, so they are the slowest), "unlike" = remove one like.
# "unsave" = remove one saved post/reel from "Saved"; "download" = fetch one chat file (photo) from the CDN.
PROFILES = {
    "Güvenli": {"unsend": (60, 120), "hide": (30, 60), "story": (20, 40), "unblock": (45, 90), "unlike": (20, 40),
                "unsave": (20, 40), "download": (1.0, 3.0), "batch": 10, "rest": (120, 240)},
    "Dengeli": {"unsend": (30, 60), "hide": (15, 30), "story": (10, 20), "unblock": (25, 50), "unlike": (10, 20),
                "unsave": (10, 20), "download": (0.5, 1.5), "batch": 15, "rest": (120, 300)},
    "Hızlı":   {"unsend": (15, 30), "hide": (8, 15), "story": (5, 10), "unblock": (12, 25), "unlike": (5, 10),
                "unsave": (5, 10), "download": (0.2, 0.6), "batch": 20, "rest": (180, 360)},
}
DEFAULT_PROFILE = "Dengeli"
SOFT_PAUSE = (300, 480)   # rest (s) after Instagram says "please wait"
MAX_SOFT_HITS = 3         # this many "please wait" warnings in a row -> long rest (or stop)
LONG_REST = (2700, 4500)  # autonomous mode: 45-75 min rest after MAX_SOFT_HITS warnings, then carry on
MAX_LONG_RESTS = 3        # ... at most this many times per run, then stop for good
NET_BACKOFF = (8, 20, 45, 90)   # seconds to wait before retrying after a connectivity error


def norm_word(text):
    """Turkish-safe, case-insensitive form of a typed confirmation word (İ/I/ı -> i)."""
    return (text or "").strip().replace("İ", "i").replace("I", "i").replace("ı", "i").lower()


class StopRequested(Exception):
    """Raised inside a worker when the user pressed Stop during a long wait."""


class Pacer:
    """Random delays with periodic long rests; slows down after every Instagram warning."""

    def __init__(self, profile):
        self.p = PROFILES.get(profile, PROFILES[DEFAULT_PROFILE])
        self.mult = 1.0
        self.count = 0
        self.next_rest = self._roll()

    def _roll(self):
        return max(3, int(self.p["batch"] * random.uniform(0.7, 1.3)))

    def delay(self, kind):
        """-> (seconds to wait, is_long_rest)"""
        lo, hi = self.p[kind]
        secs = random.uniform(lo, hi) * self.mult
        self.count += 1
        if self.count >= self.next_rest:
            self.count, self.next_rest = 0, self._roll()
            return secs + random.uniform(*self.p["rest"]), True
        return secs, False

    def slow_down(self):
        self.mult = min(self.mult * 1.5, 4.0)

    @staticmethod
    def estimate(profile, kind, n):
        """Expected total seconds for n actions."""
        p = PROFILES.get(profile, PROFILES[DEFAULT_PROFILE])
        avg = sum(p[kind]) / 2
        return n * avg + (n / p["batch"]) * (sum(p["rest"]) / 2)


def fmt_duration(seconds):
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds} sn"
    if seconds < 5400:
        return f"{seconds / 60:.0f} dk"
    return f"{seconds / 3600:.1f} saat"


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return default


def save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


def limit_kind(e):
    """None, 'soft' (rest, slow down, retry) or 'hard' (stop right now)."""
    text = f"{type(e).__name__} {e}".lower()
    if isinstance(e, (FeedbackRequired, ChallengeRequired, LoginRequired)) or any(
            k in text for k in ("feedback_required", "feedbackrequired", "challenge", "login_required",
                                "loginrequired", "checkpoint", "spam", "sentryblock")):
        return "hard"
    if isinstance(e, (PleaseWaitFewMinutes, RateLimitError, ClientThrottledError)) or any(
            k in text for k in ("please wait", "pleasewait", "429", "rate limit", "ratelimit", "throttl",
                                "too many", "toomany")):
        return "soft"
    return None


def is_limit_error(e):
    return limit_kind(e) is not None


_NET_WORDS = ("connection", "timed out", "timeout", "temporary failure", "name resolution", "getaddrinfo",
              "network is unreachable", "max retries", "remote end closed", "eof occurred", "curl: (",
              "could not resolve", "recv failure", "reset by peer", "broken pipe", "clientconnectionerror")


def is_network_error(e):
    """Transient connectivity problem (Wi-Fi drop, DNS, timeout) - worth retrying, not an Instagram verdict."""
    if isinstance(e, BlockedDestination) or limit_kind(e):
        return False
    if isinstance(e, (ConnectionError, TimeoutError)):
        return True
    text = f"{type(e).__name__} {e}".lower()
    return any(w in text for w in _NET_WORDS)


def friendly(e):
    if isinstance(e, BlockedDestination):
        return f"Güvenlik kilidi bağlantıyı engelledi: {e}"
    if "out of date" in str(e).lower() or "needs_upgrade" in str(e).lower():
        return ("Instagram bu programın kullandığı uygulama sürümünü artık kabul etmiyor (şifreyle girişte bilinen "
                "sorun, özellikle 2 adımlı doğrulamalı hesaplarda). Şifre veya kodun yanlış değil. "
                "Sağdaki 'B · Tarayıcı oturumuyla giriş' yöntemini dene.")
    if isinstance(e, BadPassword):
        return "Kullanıcı adı veya şifre hatalı."
    if isinstance(e, ChallengeRequired):
        return ("Instagram ek doğrulama istiyor. Instagram uygulamasında 'Bu bendim' bildirimini onayla, "
                "sonra tekrar dene.")
    if isinstance(e, LoginRequired):
        return "Instagram oturumun süresi dolmuş. Çıkış yapıp tekrar giriş yap."
    if is_limit_error(e):
        return "Instagram hesabı geçici olarak sınırladı / uyardı. Birkaç saat bekleyip tekrar dene."
    if is_network_error(e):
        return "Bağlantı sorunu: internet bağlantını kontrol et (işlem bağlantı gelince kendiliğinden yeniden denenir)."
    return str(e) or type(e).__name__
