"""POST /api/finalize - the call has ended: build the lead, the designer's handoff note, send it to Telegram, store it."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler
from datetime import datetime
import uuid
from _http import read_json, send, clamp_transcript
import _core as c
import _store
import _hubspot


def ts(v, default):
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else default
    except ValueError:
        return default


def process_finalize(b):
    now = datetime.now(c.IST)
    started = ts(b.get("started_at"), now)
    ended = ts(b.get("ended_at"), now)
    transcript = clamp_transcript(b.get("transcript"))
    allf = {"project", "location", "timeline", "size", "property_state", "name", "slot"}
    facts = c.clean_facts(b.get("facts"))
    dec = c.evaluate(facts, now, allf if b.get("ended_by") == "agent" else ())
    phone = b.get("phone") or None

    if dec["decision"] == "escalate":
        outcome, label = "escalated", "Escalated to studio head"
        note = c.build_escalation_note(facts, phone, started, transcript)
    elif dec["decision"] == "decline":
        outcome, label = "closed", "Closed - " + dec["reason"].replace("_", " ")
        note = c.build_decline_note(facts, dec, phone, started)
    elif dec["decision"] == "forward":
        outcome, label = "qualified", "Qualified - sent to designer"
        note = c.build_note(facts, dec, phone, started, len(transcript))
    else:  # caller hung up mid-qualification (T17-style): never lose them - queue a call-back
        outcome, label = "callback", "Call dropped - call-back queued"
        note = c.build_note(facts, dict(dec, flags=dec.get("flags", []) + ["CALL ENDED EARLY - caller hung up before the questions were finished; call back"]), phone, started, len(transcript))
    first_reply = b.get("first_response_secs")
    lead = {
        "id": b.get("lead_id") or ("L" + uuid.uuid4().hex[:8]),
        "created_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_secs": max(1, int((ended - started).total_seconds())),
        "channel": "phone",
        "after_hours": c.after_hours(started),
        "phone": phone,
        "name": facts["caller_name"],
        "outcome": outcome,
        "label": label,
        "reason": dec.get("reason"),
        "priority": dec.get("priority") if outcome in ("qualified", "callback") else ("URGENT" if outcome == "escalated" else None),
        "facts": facts,
        "criteria": dec.get("criteria"),
        "flags": dec.get("flags", []),
        "note": note,
        "transcript": transcript,
        "first_response_secs": first_reply if first_reply is not None else 1.0,
        "handoff": {"channel": "telegram", "sent": False},
        "claimed_at": None,
        "usage": b.get("usage", {"input": 0, "output": 0}),
        "llm_cost_inr": b.get("cost_inr", 0),
        "model": b.get("model") or c.model_name(),
        "asked_price": bool(facts["asked_price"]),
        "price_blocked": int(b.get("price_blocked", 0)),
        "demo": bool(b.get("demo", True)),
    }
    slot = facts.get("preferred_slot")
    lead["next_action"] = {
        "qualified": "Designer calls back %s to confirm the consultation%s." % ("next morning at 10" if lead["after_hours"] else "within 30 minutes", (" (caller prefers " + slot + ")") if slot else ""),
        "callback": "Call back to finish the questions (the call ended early).",
        "escalated": "Senior person calls back within 15 minutes; do not route to sales.",
        "closed": "No designer time needed. Reason: %s." % (dec.get("reason") or "").replace("_", " "),
    }[outcome]
    if outcome in ("qualified", "callback", "escalated"):
        lead["handoff"] = c.send_telegram(note, lead["id"], urgent=(outcome == "escalated"))
        lead["handoff"]["channel"] = "telegram"
        lead["handoff"]["at"] = datetime.now(c.IST).isoformat()
    if _hubspot.configured():
        lead["hubspot"] = _hubspot.sync_lead(lead)
    stored = False
    if _store.configured():
        try:
            _store.save(lead)
            stored = True
        except Exception as e:
            lead["store_error"] = str(e)[:120]
    return {"lead": lead, "stored": stored}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            send(self, process_finalize(read_json(self)))
        except Exception as e:
            send(self, {"error": str(e)[:200]}, 500)

    def log_message(self, *a):
        pass
