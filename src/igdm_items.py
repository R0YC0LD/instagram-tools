"""
igdm_items.py
Small helpers for reading Instagram direct-message items (id, text, label, time).
"""

from datetime import datetime


ITEM_LABELS = {
    "media": "[Fotoğraf/Video]", "raven_media": "[Geçici medya]", "voice_media": "[Sesli mesaj]",
    "like": "[Beğeni]", "link": "[Bağlantı]", "reel_share": "[Reel paylaşımı]",
    "media_share": "[Gönderi paylaşımı]", "clip": "[Klip]", "animated_media": "[GIF]",
    "story_share": "[Hikaye paylaşımı]", "felix_share": "[Video paylaşımı]",
    "action_log": "[Sistem mesajı]", "xma_link": "[Bağlantı]", "generic_xma": "[Paylaşım]",
}


def item_id(it):
    return it.get("item_id") or it.get("id") or it.get("client_context")


def item_text(it):
    text = it.get("text")
    if not text and it.get("item_type") == "link":
        text = (it.get("link") or {}).get("text")
    return text or ""


def item_label(it):
    return item_text(it) or ITEM_LABELS.get(it.get("item_type"), f"[{it.get('item_type', 'diğer')}]")


def item_time(it):
    try:
        return datetime.fromtimestamp(int(it["timestamp"]) / 1_000_000).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""
