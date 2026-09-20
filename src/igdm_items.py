"""
igdm_items.py
Small helpers for reading Instagram direct-message items (id, text, label, time).
"""

from datetime import datetime

from igdm_i18n import tr, T


ITEM_LABELS = {
    "media": T("[Fotoğraf/Video]"), "raven_media": T("[Geçici medya]"), "voice_media": T("[Sesli mesaj]"),
    "like": T("[Beğeni]"), "link": T("[Bağlantı]"), "reel_share": T("[Reel paylaşımı]"),
    "media_share": T("[Gönderi paylaşımı]"), "clip": T("[Klip]"), "animated_media": T("[GIF]"),
    "story_share": T("[Hikaye paylaşımı]"), "felix_share": T("[Video paylaşımı]"),
    "action_log": T("[Sistem mesajı]"), "xma_link": T("[Bağlantı]"), "generic_xma": T("[Paylaşım]"),
}


def item_id(it):
    return it.get("item_id") or it.get("id") or it.get("client_context")


def item_text(it):
    text = it.get("text")
    if not text and it.get("item_type") == "link":
        text = (it.get("link") or {}).get("text")
    return text or ""


def item_label(it):
    return item_text(it) or tr(ITEM_LABELS[it.get("item_type")]) if it.get("item_type") in ITEM_LABELS else (item_text(it) or tr("[{0}]", it.get("item_type", tr("diğer"))))


def item_time(it):
    try:
        return datetime.fromtimestamp(int(it["timestamp"]) / 1_000_000).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""
