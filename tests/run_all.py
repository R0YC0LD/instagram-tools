"""Runs every tests/test_*.py in its own process and prints a summary (exit code 1 if anything failed)."""
import glob
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
files = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
failed, total_pass = [], 0
t0 = time.time()
for f in files:
    name = os.path.basename(f)
    t = time.time()
    try:
        p = subprocess.run([sys.executable, f], capture_output=True, text=True, timeout=600, encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        ok = p.returncode == 0 and "Traceback" not in out and "FAIL" not in out
    except subprocess.TimeoutExpired:
        out, ok = "TIMEOUT", False
    n = len(re.findall(r"^PASS", out, re.M))
    total_pass += n
    print(f"{'OK  ' if ok else 'FAIL'} {name:<32} {n:>3} checks  {time.time() - t:5.1f}s")
    if not ok:
        failed.append(name)
        print("\n".join("      " + line for line in out.strip().splitlines()[-15:]))
print(f"\n{total_pass} checks passed in {time.time() - t0:.0f}s across {len(files)} files" + (f"  -  FAILED: {', '.join(failed)}" if failed else "  -  ALL GOOD"))
sys.exit(1 if failed else 0)