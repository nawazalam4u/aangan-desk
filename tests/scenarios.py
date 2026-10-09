"""Plays every demo scenario through the agent (no key needed) and prints where each ends."""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))
if not os.environ.get("LIVE"):
    os.environ.pop("ANTHROPIC_API_KEY", None); os.environ.pop("GEMINI_API_KEY", None)
import turn, finalize, _core as c

import json
SC = json.load(open(os.path.join(ROOT, "public", "scenarios.json"), encoding="utf-8"))
EXPECT = {"Qualified home (asks price)": "qualified", "Startup office": "qualified", "Out of area (Nashik)": "closed", "Budget far too low": "closed",
          "Needs it in 3 weeks": "closed", "Only wants ideas": "closed", "Restaurant": "closed", "Angry existing client": "escalated", "Call drops midway": "callback"}
bad = 0
for sc in SC:
    label, opening, a, hang = sc["label"], sc["open"], sc["a"], sc.get("hangAfter")
    tr = [{"role": "agent", "text": c.GREETING}]; facts = None; asked = {}; line = opening; ended = "agent"
    for n in range(16):
        tr.append({"role": "caller", "text": line})
        r = turn.process_turn({"transcript": tr, "facts": facts, "asked": asked}); facts, asked = r["facts"], r["asked"]
        tr.append({"role": "agent", "text": r["reply"]})
        assert not c._PRICE_PAT.search(r["reply"].replace(c.APPROVED_PRICING_LINE, "")), r["reply"]
        if hang and n + 1 >= int(hang): ended = "caller"; break
        if r["done"]: break
        line = a.get(r["decision"]["ask"], "I'm not sure yet.")
    out = finalize.process_finalize({"transcript": tr, "facts": facts, "phone": "+91 90000 00000", "ended_by": ended})["lead"]
    ok = out["outcome"] == EXPECT[label]; bad += not ok
    print(("OK  " if ok else "FAIL"), label.ljust(30), out["outcome"].ljust(10), out["priority"], "| turns:", sum(m["role"] == "caller" for m in tr), "|", (out["reason"] or ""))
# guardrail attack
for s in ["It would cost around 2000 per sq ft", "Our rates start at ₹1,800", "roughly 12 lakh", "a 2BHK is typically 15L", "Rs. 500 per square foot", "starts from 3.5 lakhs"]:
    assert c.guard_reply(s)[1], s
for s in ["Thank you, I have noted your 1,400 sq ft flat in Kothrud.", "Someone will call you within 30 minutes."]:
    assert not c.guard_reply(s)[1], s
print("guardrail: 6/6 price leaks blocked, 2/2 normal sentences allowed")
sys.exit(1 if bad else 0)
