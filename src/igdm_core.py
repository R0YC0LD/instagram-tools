"""
igdm_core.py  -  security core of the app (no GUI).

  * Network allowlist: only Instagram/Facebook hosts may be contacted. Any other destination (including bare
    IP addresses) is refused, so a compromised dependency cannot ship data to a third-party server.
    Two layers: Python sockets/DNS and every HTTP request URL (this also covers the native libcurl transport
    that instagrapi uses, which does not go through Python sockets).
  * The saved session is encrypted with Windows DPAPI (bound to the current Windows user account) and stored in
    %LOCALAPPDATA%/IGDMTool. Saving is opt-in and the password itself is never written to disk.

Importing this module installs the network guard.
"""

import os
import json
import socket
import ctypes
import ctypes.wintypes as wt
from urllib.parse import urlparse
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Network allowlist (anti-exfiltration)
# ---------------------------------------------------------------------------
ALLOWED_DOMAINS = ("instagram.com", "cdninstagram.com", "facebook.com", "fbcdn.net")


class BlockedDestination(OSError):
    pass


def _host_allowed(host: Optional[str]) -> bool:
    if not host:
        return False
    host = host.strip("[]").rstrip(".").lower()
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


def _block(host: Any) -> None:
    raise BlockedDestination(f"Blocked connection to non-Instagram host: {host!r}")


def install_network_guard() -> None:
    """Refuse every outbound connection that is not to an allowed Instagram host."""
    # Layer 1: any DNS lookup or connect made through Python sockets.
    real_getaddrinfo = socket.getaddrinfo
    resolved_ips = set()

    def guarded_getaddrinfo(host, *args, **kwargs):
        if isinstance(host, bytes):
            host = host.decode("ascii", "ignore")
        if not _host_allowed(host):
            _block(host)
        result = real_getaddrinfo(host, *args, **kwargs)
        for entry in result:
            resolved_ips.add(entry[4][0])
        return result

    socket.getaddrinfo = guarded_getaddrinfo

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _check_address(address):
        if isinstance(address, tuple) and address and address[0] not in resolved_ips:
            _block(address[0])

    def guarded_connect(self, address):
        _check_address(address)
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        _check_address(address)
        return real_connect_ex(self, address)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex

    # Layer 2: HTTP request URLs, which also covers the native libcurl transport
    # that instagrapi uses by default (libcurl does not go through Python sockets).
    import requests

    real_send = requests.sessions.Session.send

    def guarded_send(self, request, **kwargs):
        if not _host_allowed(urlparse(request.url).hostname):
            _block(urlparse(request.url).hostname)
        return real_send(self, request, **kwargs)

    requests.sessions.Session.send = guarded_send

    try:
        from curl_cffi import requests as curl_requests

        real_curl_request = curl_requests.Session.request

        def guarded_curl_request(self, method, url, *args, **kwargs):
            if not _host_allowed(urlparse(str(url)).hostname):
                _block(urlparse(str(url)).hostname)
            return real_curl_request(self, method, url, *args, **kwargs)

        curl_requests.Session.request = guarded_curl_request
    except ImportError:
        pass


install_network_guard()

from instagrapi import Client  # noqa: E402  (imported after the guard is active)

# ---------------------------------------------------------------------------
# Encrypted session storage (Windows DPAPI)
# ---------------------------------------------------------------------------
APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "IGDMTool")
SESSION_FILE = os.path.join(APP_DIR, "session.bin")
_ENTROPY = b"IGDMTool-session-v1"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.c_void_p)]


def _make_blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.c_void_p)), buf


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    inp, inp_buf = _make_blob(data)
    ent, ent_buf = _make_blob(_ENTROPY)
    out = _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    # Same argument shape for both calls; 0x1 = CRYPTPROTECT_UI_FORBIDDEN
    if not fn(ctypes.byref(inp), None, ctypes.byref(ent), None, None, 0x1, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)



def wipe_session(session_file: str = SESSION_FILE) -> bool:
    """Overwrite the session file with random bytes, then delete it."""
    try:
        if not os.path.exists(session_file):
            return False
        size = os.path.getsize(session_file)
        with open(session_file, "r+b") as fp:
            fp.write(os.urandom(max(size, 1)))
            fp.flush()
            os.fsync(fp.fileno())
        os.remove(session_file)
        return True
    except OSError:
        return False


def load_session(client: Client, session_file: str = SESSION_FILE) -> bool:
    """Load and verify the encrypted session"""
    if not os.path.exists(session_file):
        return False
    try:
        with open(session_file, "rb") as fp:
            settings = json.loads(_dpapi(fp.read(), protect=False).decode("utf-8"))
    except Exception:
        # Not decryptable by this Windows account (or corrupt): unusable, remove it.
        wipe_session(session_file)
        return False
    try:
        client.set_settings(settings)
        client.account_info()
        return True
    except BlockedDestination:
        raise
    except Exception:
        wipe_session(session_file)
        return False


def save_session(client: Client, session_file: str = SESSION_FILE) -> bool:
    """Save session encrypted with DPAPI (atomic write)"""
    try:
        os.makedirs(os.path.dirname(session_file), exist_ok=True)
        blob = _dpapi(json.dumps(client.get_settings()).encode("utf-8"), protect=True)
        tmp = session_file + ".tmp"
        with open(tmp, "wb") as fp:
            fp.write(blob)
        os.replace(tmp, session_file)
        return True
    except Exception:
        return False
