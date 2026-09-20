"""
igdm_perf.py
Smoothness helpers: read the monitor's refresh rate so animations/polling run at the display's pace
(60 / 120 / 144 / 240 Hz ...), and give the UI thread more CPU slices while the heavy modules load.
Tiny and dependency-free.
"""

import ctypes
import sys
from contextlib import contextmanager


class _DEVMODE(ctypes.Structure):
    _fields_ = [("dmDeviceName", ctypes.c_wchar * 32), ("dmSpecVersion", ctypes.c_ushort),
                ("dmDriverVersion", ctypes.c_ushort), ("dmSize", ctypes.c_ushort), ("dmDriverExtra", ctypes.c_ushort),
                ("dmFields", ctypes.c_ulong), ("dmPositionX", ctypes.c_long), ("dmPositionY", ctypes.c_long),
                ("dmDisplayOrientation", ctypes.c_ulong), ("dmDisplayFixedOutput", ctypes.c_ulong),
                ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short), ("dmYResolution", ctypes.c_short),
                ("dmTTOption", ctypes.c_short), ("dmCollate", ctypes.c_short), ("dmFormName", ctypes.c_wchar * 32),
                ("dmLogPixels", ctypes.c_ushort), ("dmBitsPerPel", ctypes.c_ulong), ("dmPelsWidth", ctypes.c_ulong),
                ("dmPelsHeight", ctypes.c_ulong), ("dmDisplayFlags", ctypes.c_ulong),
                ("dmDisplayFrequency", ctypes.c_ulong)]


_cached = None


def refresh_rate_hz(default=60):
    """Current refresh rate of the primary display in Hz (cached; 60 if it cannot be read)."""
    global _cached
    if _cached is None:
        hz = default
        try:
            dm = _DEVMODE()
            dm.dmSize = ctypes.sizeof(_DEVMODE)
            if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)):   # ENUM_CURRENT_SETTINGS
                hz = int(dm.dmDisplayFrequency) or default
        except Exception:
            pass
        _cached = min(max(hz, 30), 360)          # "1" / "0" mean "hardware default" on some drivers
        if _cached < 50:
            _cached = default
    return _cached


def frame_ms():
    """Length of one display frame in whole milliseconds (>= 4 ms, the practical Tk timer floor)."""
    return max(4, int(1000 / refresh_rate_hz()))


@contextmanager
def responsive_ui(switch_interval=0.0005):
    """While heavy modules import on a worker thread, switch GIL slices faster so the UI thread keeps animating."""
    old = sys.getswitchinterval()
    sys.setswitchinterval(switch_interval)
    try:
        yield
    finally:
        sys.setswitchinterval(old)
