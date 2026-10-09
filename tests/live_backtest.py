"""Same 40 enquiries, but facts are extracted by the REAL AI (needs GEMINI_API_KEY or ANTHROPIC_API_KEY)."""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "api")); sys.path.insert(0, HERE)
import _core as c
from enquiries import E
assert c.provider() != "none", "set an API key first"
ok = n = 0; cost = 0.0; bad = []
for i, e in E.items():
    if not e["lines"]:
        continue
    tr = [{"role": "agent", "text": c.GREETING}]
    for ln in e["lines"]:
        tr += [{"role": "caller", "text": ln}, {"role": "agent", "text": "Okay, thank you."}]
    f, u = c.extract_facts(tr, None, e["ts"]); cost += c.cost_inr(u)
    dec = c.evaluate(f, e["ts"]); good = dec["qual"] in e["gold"]; n += 1; ok += good
    if not good: bad.append((i, e["gold"], dec["qual"], dec.get("reason"), f.get("project_type"), f.get("notes")))
    print(("OK  " if good else "MISS"), i, "gold=%s" % "/".join(sorted(e["gold"])), "got=%s" % dec["qual"], dec.get("reason") or "")
print("\nLive AI: %d/%d agree | extraction cost for all %d: Rs %.2f (Rs %.3f each)" % (ok, n, n, cost, cost / n))
for b in bad: print("MISS detail:", b)
