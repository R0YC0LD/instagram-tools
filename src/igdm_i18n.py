"""
igdm_i18n.py
Tiny translation layer (no dependencies, safe to import before anything heavy).

  tr("Türkçe kaynak metin {0}", value)   -> text in the current language (Turkish text is the key)
  T("Türkçe kaynak metin")               -> marker for class/module-level constants; translate at use with tr()

Turkish is the source language: with language "tr" nothing is looked up. Other languages are dictionaries
in igdm_lang_<code>.py mapping the Turkish text to the translation (same {0}, {1} placeholders).
A missing entry falls back to Turkish (and is remembered in `missing()` so the test-suite can catch it).
"""

import json
import os

LANGS = (("tr", "Türkçe"), ("en", "English"))
CODES = tuple(c for c, _ in LANGS)
NAMES = dict(LANGS)

APP_NAMES = {"tr": "Instagram Araçları", "en": "Instagram Tools"}

_APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "IGDMTool")
_state = {"lang": "tr"}
_catalogs = {}
_missing = set()


class TStr(str):
    """A translated string that remembers the Turkish text it was built from (`.src`), e.g. so the log
    can pick its colour from Turkish keywords whatever the display language is."""
    src = ""


def T(text):
    """Marker for constants defined at import time; the real translation happens where they are used."""
    return text


def get_language():
    return _state["lang"]


def set_language(code):
    if code in CODES:
        _state["lang"] = code
    return _state["lang"]


def system_language():
    """'tr' when Windows' display language is Turkish, otherwise 'en'."""
    try:
        import ctypes
        return "tr" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x1F else "en"
    except Exception:
        return "en"


def initial_language():
    """The language saved in the settings file, else the OS language."""
    try:
        with open(os.path.join(_APP_DIR, "settings.json"), "r", encoding="utf-8") as fp:
            code = json.load(fp).get("language")
        if code in CODES:
            return code
    except Exception:
        pass
    return system_language()


def catalog(code):
    if code not in _catalogs:
        try:
            mod = __import__(f"igdm_lang_{code}")
            _catalogs[code] = mod.CATALOG
        except ImportError:
            _catalogs[code] = {}
    return _catalogs[code]


def missing():
    return set(_missing)


def app_title():
    return APP_NAMES.get(_state["lang"], APP_NAMES["tr"])


def tr(text, *args, **kw):
    """Translate `text` (Turkish source) into the current language and fill the placeholders."""
    text = str(text)
    out = text
    lang = _state["lang"]
    if lang != "tr":
        found = catalog(lang).get(text)
        if found is None:
            _missing.add(text)
        else:
            out = found
    src = text
    if args or kw:
        try:
            src = text.format(*args, **kw)
        except (IndexError, KeyError, ValueError):
            src = text
        try:
            out = out.format(*args, **kw)
        except (IndexError, KeyError, ValueError):
            out = src                            # a broken translation must never crash the UI
    s = TStr(out)
    s.src = src
    return s
