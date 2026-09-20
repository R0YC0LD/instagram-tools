"""
i18n_keys.py  -  collects every translatable string used in src/ (first argument of tr(...) / T(...)).

  python tools/i18n_keys.py            # prints them in source order
  from i18n_keys import collect        # used by tests/test_i18n.py to prove the catalogs are complete
"""
import ast
import os
import re
import sys

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
PLACEHOLDER = re.compile(r"\{(\d+|[a-zA-Z_]\w*)[^}]*\}")


def collect(src_dir=SRC):
    """-> list of (key, "file.py:line") in source order, duplicates removed."""
    seen, out = set(), []
    for fn in sorted(os.listdir(src_dir)):
        if not fn.endswith(".py") or fn == "igdm_assets.py" or fn.startswith("igdm_lang_"):
            continue
        with open(os.path.join(src_dir, fn), encoding="utf-8") as fp:
            tree = ast.parse(fp.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "T")
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                key = node.args[0].value
                if key not in seen:
                    seen.add(key)
                    out.append((key, f"{fn}:{node.lineno}"))
    return out


def placeholders(text):
    return sorted(m.group(1) for m in PLACEHOLDER.finditer(text.replace("{{", "").replace("}}", "")))


if __name__ == "__main__":
    keys = collect()
    for k, where in keys:
        print(f"{where:24s} {k!r}")
    print(f"\n{len(keys)} unique strings", file=sys.stderr)
