#!/usr/bin/env python3
"""Reusable QA gate for ED_AP.py service-extraction refactors (Phase 2.x).

Deterministic, cheap replacement for the QA subagent. Run from the repo root
with the repo's venv python. Checks:
  1. import invariants (ED_AP, EDAPGui, and the new service module standalone)
  2. routing grep invariants (methods gone from ED_AP; no stale self.<name>(
     in ED_AP; no self.ap.<name>( intra-service misroute in the service)
  3. per-method behaviour parity vs git HEAD:ED_AP.py (normalize self.ap.->self.,
     ignore blank lines and added deferred `from ED_AP import ...` lines)

Usage:
  python qa_service_extraction.py \
      --service-file services/jump_service.py \
      --service-module services.jump_service \
      --names honk,position,jump,fsd_assist \
      [--extra-file EDShipControl.py --extra-file EDAPGui.py]

Exit code 0 == all PASS, 1 == at least one FAIL.
"""
import argparse
import re
import subprocess
import sys


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def extract_method(src, name):
    """Return the list of body lines of method `name` (def line + body),
    right-stripped, from python source `src`. Indentation-based; assumes a
    single unique `def <name>(` at method indent."""
    lines = src.splitlines()
    out = []
    ind = None
    for i, l in enumerate(lines):
        s = l.lstrip()
        if ind is None:
            if re.match(r"def\s+" + re.escape(name) + r"\s*\(", s) and (l[: len(l) - len(s)]).strip() == "":
                ind = len(l) - len(s)
                out.append(l.rstrip())
            continue
        # already inside the method
        if l.strip() == "":
            out.append("")
            continue
        cur = len(l) - len(l.lstrip())
        if cur <= ind and (l.lstrip().startswith(("def ", "class ", "@"))):
            break
        out.append(l.rstrip())
    return out


def norm_body(lines, drop_deferred=True):
    """Normalize a body for parity comparison: strip blanks, drop added
    deferred/future imports, collapse `self.ap.`->`self.`."""
    res = []
    for l in lines:
        t = l.rstrip()
        if t.strip() == "":
            continue
        st = t.strip()
        if drop_deferred and (st.startswith("from ED_AP import") or st.startswith("from __future__ import")):
            continue
        res.append(t.replace("self.ap.", "self."))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--service-file", required=True)
    ap.add_argument("--service-module", required=True)
    ap.add_argument("--names", required=True, help="comma-separated moved method names")
    ap.add_argument("--python", default=r".\venv\Scripts\python.exe")
    args = ap.parse_args()
    names = [n.strip() for n in args.names.split(",") if n.strip()]

    fails = []
    py = args.python

    def check(label, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {detail}" if detail and not ok else ""))
        if not ok:
            fails.append(label)

    # --- 1. imports ---
    rc, _ = run([py, "-c", "import ED_AP; import EDAPGui"])
    check("import ED_AP + EDAPGui", rc == 0)
    rc, out = run([py, "-c", f"import {args.service_module} as m; print('OK')"])
    check(f"import {args.service_module} standalone", rc == 0 and "OK" in out, out.strip()[-300:])

    # --- read files ---
    edap = open("ED_AP.py", encoding="utf-8").read()
    svc = open(args.service_file, encoding="utf-8").read()

    # --- 2. routing invariants ---
    for n in names:
        check(f"ED_AP has no `def {n}`", re.search(r"^\s*def\s+" + re.escape(n) + r"\s*\(", edap, re.M) is None)
    for n in names:
        # stale direct call in ED_AP (ignore commented lines)
        stale = [l for l in edap.splitlines()
                 if re.search(r"self\." + re.escape(n) + r"\s*\(", l) and not l.lstrip().startswith("#")]
        check(f"ED_AP no stale self.{n}(", not stale, " | ".join(stale[:3]))
    for n in names:
        mis = [l for l in svc.splitlines()
               if re.search(r"self\.ap\." + re.escape(n) + r"\s*\(", l)]
        check(f"{args.service_file} no self.ap.{n}( misroute", not mis, " | ".join(mis[:3]))
    # module-top ED_AP import in service = circular-import risk
    top = [l for l in svc.splitlines() if re.match(r"(from ED_AP import|import ED_AP)\b", l)]
    check(f"{args.service_file} no module-top ED_AP import", not top, " | ".join(top[:3]))

    # --- 3. parity vs HEAD ---
    rc, head = run(["git", "show", "HEAD:ED_AP.py"])
    if rc != 0:
        check("git show HEAD:ED_AP.py", False, head.strip()[-200:])
    else:
        for n in names:
            o = norm_body(extract_method(head, n))
            new = norm_body(extract_method(svc, n))
            ok = o == new
            check(f"parity {n}", ok)
            if not ok:
                # show first differing line for diagnosis
                import difflib
                d = [x for x in difflib.unified_diff(o, new, lineterm="") if x and x[0] in "+-" and not x.startswith(("+++", "---"))]
                print("       diff> " + " || ".join(d[:6]))

    print("\n=== " + ("ALL PASS" if not fails else f"{len(fails)} FAIL: " + ", ".join(fails)) + " ===")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
