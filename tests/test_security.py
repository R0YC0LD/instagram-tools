import os, sys
SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, SRC)
import sys, os, socket, tempfile
pass
import igdm_core as t
import requests

ok = True
def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok = ok and cond

# DPAPI round trip + ciphertext does not contain plaintext
secret = b'{"authorization_data": "TOPSECRET-TOKEN"}'
enc = t._dpapi(secret, True)
check("dpapi ciphertext hides plaintext", b"TOPSECRET" not in enc)
check("dpapi round trip", t._dpapi(enc, False) == secret)

# session save/load through files, with a fake client
class Fake:
    def get_settings(self): return {"a": 1, "token": "TOPSECRET-TOKEN"}
p = os.path.join(tempfile.mkdtemp(), "s.bin")
check("save_session", t.save_session(Fake(), p))
check("file has no plaintext", b"TOPSECRET" not in open(p, "rb").read())
check("wipe_session", t.wipe_session(p) and not os.path.exists(p))

# allowlist logic
check("allow i.instagram.com", t._host_allowed("i.instagram.com"))
check("allow scontent.cdninstagram.com", t._host_allowed("scontent.cdninstagram.com"))
check("block evil.com", not t._host_allowed("evil.com"))
check("block instagram.com.evil.com", not t._host_allowed("instagram.com.evil.com"))
check("block notinstagram.com", not t._host_allowed("notinstagram.com"))
check("block IP literal", not t._host_allowed("8.8.8.8"))

# guard actually blocks
def blocked(fn):
    try:
        fn(); return False
    except (t.BlockedDestination, requests.exceptions.RequestException, OSError) as e:
        return "Blocked" in str(e) or isinstance(e, t.BlockedDestination)
check("socket.getaddrinfo(example.com) blocked", blocked(lambda: socket.getaddrinfo("example.com", 443)))
check("requests.get(example.com) blocked", blocked(lambda: requests.get("https://example.com", timeout=5)))
check("requests.get(IP) blocked", blocked(lambda: requests.get("https://1.1.1.1", timeout=5)))
check("raw connect to IP blocked", blocked(lambda: socket.create_connection(("1.1.1.1", 443), timeout=5)))

# guard allows Instagram (network reachability only, no login)
try:
    r = requests.get("https://i.instagram.com/", timeout=10)
    check("instagram reachable through guard (HTTP %s)" % r.status_code, True)
except t.BlockedDestination:
    check("instagram reachable through guard", False)
except Exception as e:
    print("INFO instagram request error (not the guard):", type(e).__name__)

# curl transport guard
try:
    from curl_cffi import requests as cr
    check("curl_cffi example.com blocked", blocked(lambda: cr.Session().request("GET", "https://example.com", timeout=5)))
except ImportError:
    print("INFO curl_cffi missing")

print("ALL OK" if ok else "SOME FAILED")
