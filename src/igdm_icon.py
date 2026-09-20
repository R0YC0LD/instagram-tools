"""
igdm_icon.py
Window-icon helpers. Deliberately light (tkinter + the embedded assets only) so it can be used by the
intro screen before the heavy modules are imported.
"""

import base64
import os
import tkinter as tk

import igdm_assets

APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "IGDMTool")
_ICO_PATH = os.path.join(APP_DIR, "app.ico")


def icon_path():
    """Write the embedded .ico into the app-data folder (Tk needs a real file) and return its path."""
    try:
        data = base64.b64decode(igdm_assets.ICON_ICO_B64)
        if not os.path.exists(_ICO_PATH) or os.path.getsize(_ICO_PATH) != len(data):
            os.makedirs(APP_DIR, exist_ok=True)
            with open(_ICO_PATH, "wb") as fp:
                fp.write(data)
        return _ICO_PATH
    except OSError:
        return None


def set_window_icon(win):
    path = icon_path()
    if path:
        try:
            win.iconbitmap(path)
        except tk.TclError:
            pass


def logo_image(large=False):
    return tk.PhotoImage(data=igdm_assets.ICON_PNG_LARGE_B64 if large else igdm_assets.ICON_PNG_B64)
