"""POST /api/turn - one conversational turn of the phone call. Stateless: the browser sends the transcript."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler
from datetime import datetime
import time
from _http import read_json, send, clamp_transcript
import _core as c

MAX_CALLER_TURNS = 14
QUAL_RETRY = 2     # ask a qualifying question at most twice
SOFT_RETRY = 1     # ask each handoff detail once


def process_turn(body):
    t0 = time.time()
    transcript = [m for m in clamp_transcript(body.get("transcript"), 40) if m["text"]]
    asked = body.get("asked") or {}            # {field: times asked}
    now = datetime.now(c.IST)
    if not transcript:
        return {"reply": c.GREETING, "facts": c.clean_facts(None), "decision": {"decision": "ask", "ask": "project"},
                "usage": {"input": 0, "output": 0}, "cost_inr": 0, "asked": {}, "done": False, "provider": c.provider(),
                "model": c.model_name(), "price_blocked": False, "ms": 0}

    c.LAST_ERROR["msg"] = None
    facts, u1 = c.extract_facts(transcript, body.get("facts"), now)
    caller_turns = sum(1 for m in transcript if m["role"] == "caller")

    skip = {fld for fld, n in asked.items() if n >= (QUAL_RETRY if fld in ("project", "location", "timeline") else SOFT_RETRY)}
    if caller_turns >= MAX_CALLER_TURNS:
        skip |= {"project", "location", "timeline", "size", "property_state", "name", "slot"}
    dec = c.evaluate(facts, now, skip)
    if dec["decision"] == "ask":
        asked[dec["ask"]] = asked.get(dec["ask"], 0) + 1

    if facts.get("asked_price") and not asked.get("_price") and dec["decision"] in ("ask", "forward"):
        dec["deflect_price"] = True      # say the approved pricing line once, not on every turn
        asked["_price"] = 1
    reply, u2, blocked = c.speak(transcript, dec, facts)
    usage = {"input": u1["input"] + u2["input"], "output": u1["output"] + u2["output"]}
    done = dec["decision"] in ("decline", "escalate", "forward")
    return {"reply": reply, "facts": facts, "decision": dec, "usage": usage, "cost_inr": c.cost_inr(usage), "asked": asked,
            "done": done, "provider": c.provider(), "model": c.model_name(), "price_blocked": blocked, "llm_error": c.LAST_ERROR["msg"],
            "ms": int((time.time() - t0) * 1000)}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            send(self, process_turn(read_json(self)))
        except Exception as e:  # a live call must never crash silently
            send(self, {"error": str(e)[:200]}, 500)

    def log_message(self, *a):
        pass
