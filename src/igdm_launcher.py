"""
igdm_launcher.py  -  program entry point.

Startup sequence (designed to feel instant):
  1. Show the window with the credits intro straight away (tkinter only, a few milliseconds).
  2. Import the heavy modules (instagrapi, pydantic, ...) in a background thread while the intro plays.
  3. Build the real UI underneath the intro; the intro ends by itself (or on click / key).
"""

import ctypes
import sys
import threading
import traceback
import tkinter as tk

from igdm_meta import APP_TITLE, VERSION
from igdm_icon import set_window_icon
from igdm_intro import Intro

APP_ID = "IGDMTool.PacmanCleaner.3"


def single_instance():
    """Refuse to run twice at once (two copies would double the request rate)."""
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\IGDMTool_single_instance")
        return ctypes.windll.kernel32.GetLastError() != 183, handle    # 183 = ERROR_ALREADY_EXISTS
    except Exception:
        return True, None


def window_size(root):
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = min(1340, sw - 40), min(860, sh - 90)
    return w, h, max((sw - w) // 2, 0), max((sh - h) // 3, 0)


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:  # own taskbar identity, so Windows shows OUR icon instead of grouping under python
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass

    first, _mutex = single_instance()          # keep the handle referenced for the life of the process
    root = tk.Tk()
    if not first:
        root.withdraw()
        from tkinter import messagebox
        messagebox.showinfo(APP_TITLE, "Program zaten açık. Aynı anda iki kopya çalıştırılamaz "
                                       "(istek hızı ikiye katlanır ve Instagram uyarısı riski artar).")
        return

    w, h, x, y = window_size(root)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.title(f"{APP_TITLE} v{VERSION}")
    root.configure(bg="#050814")
    root._igdm_sized = True                    # tells App not to resize/re-centre again
    set_window_icon(root)

    state = {"intro": None, "app": None}
    def focus_login():
        app = state.get("app")
        if app is not None and not (state["intro"] and not state["intro"].done):
            try:
                app.ent_user.focus_set()
            except Exception:
                pass

    state["intro"] = Intro(root, on_done=focus_login)
    root.update()

    box = {}

    def load_heavy():
        try:
            import igdm_app                # noqa: WPS433 - the heavy import, off the UI thread
            box["gui"] = igdm_app
        except BaseException as e:             # noqa: BLE001
            box["error"] = (e, traceback.format_exc())

    threading.Thread(target=load_heavy, daemon=True).start()

    def poll():
        if "gui" in box:
            try:
                state["app"] = box["gui"].App(root)
                if state["intro"] and not state["intro"].done:
                    state["intro"].lift()      # the freshly built UI must stay below the intro
                else:
                    focus_login()
            except BaseException as e:         # noqa: BLE001
                fail(e, traceback.format_exc())
        elif "error" in box:
            fail(*box["error"])
        else:
            root.after(30, poll)

    def fail(err, tb):
        if state["intro"]:
            state["intro"].finish()
        from tkinter import messagebox
        messagebox.showerror(APP_TITLE, f"Program başlatılamadı:\n\n{err}\n\nAyrıntı:\n{tb[-900:]}")
        root.destroy()

    root.after(30, poll)
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())
