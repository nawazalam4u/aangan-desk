"""Back-test: run the 40 real September enquiries through the rules engine (no API key needed).
Run:  python3 -I tests/backtest.py        (from the aangan-desk folder)
Also writes data/backtest.json, which the dashboard shows as the September baseline.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, HERE)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)

import _core as c          # noqa: E402
from enquiries import E    # noqa: E402


def run():
    rows, ok = [], 0
    for i, e in E.items():
        if not e["lines"]:
            rows.append({"id": i, "channel": e["channel"], "gold": sorted(e["gold"]), "got": "ask", "ok": True,
                         "why": "missed call - the AI would have answered", "happened": e["happened"], "resp": e["resp"], "ts": e["ts"].isoformat()})
            ok += 1
            continue
        f = c.heuristic_extract(e["lines"], e["ts"])
        dec = c.evaluate(f, e["ts"])
        got = dec["qual"]
        good = got in e["gold"]
        ok += good
        why = "; ".join("%d:%s" % (k, v["status"]) for k, v in sorted(dec["criteria"].items()))
        rows.append({"id": i, "channel": e["channel"], "gold": sorted(e["gold"]), "got": got, "ok": good, "why": why,
                     "reason": dec.get("reason"), "facts": {k: v for k, v in f.items() if v not in (None, False)},
                     "happened": e["happened"], "resp": e["resp"], "ts": e["ts"].isoformat(), "priority": dec.get("priority")})
    return rows, ok


if __name__ == "__main__":
    rows, ok = run()
    for r in rows:
        print(("OK  " if r["ok"] else "MISS"), r["id"], r["channel"][:5].ljust(5), "gold=%s" % "/".join(r["gold"]), "got=%s" % r["got"], "|", r["why"])
    phone = [r for r in rows if r["channel"] == "phone"]
    print("\nAll 40: %d/%d agree with the rubric reading | phone (build scope): %d/%d" % (ok, len(rows), sum(r["ok"] for r in phone), len(phone)))
    if "--write" in sys.argv:
        json.dump(rows, open(os.path.join(ROOT, "public", "data", "backtest.json"), "w"), indent=1)
    sys.exit(0 if ok == len(rows) else 1)
