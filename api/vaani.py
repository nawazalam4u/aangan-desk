"""POST /api/vaani?key=<VAANI_WEBHOOK_SECRET> - webhook for the Vaani voice agent (the real phone agent).

Vaani handles the live call (phone number, listening, speaking). When the call is over it posts
`call_postprocessing` with the transcript. We then run the SAME brain as everywhere else: extract facts,
apply Nikhil's five rules in code, audit the agent's words for any price, and send the result to
Telegram, Neon, HubSpot and the dashboard. `call_started` gives us the caller's number."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from _http import read_json, send
import _core as c
import _store
import finalize

LINE = re.compile(r"(?:\[[^\]]*\]\s*)?(AGENT|USER|ASSISTANT|BOT|CUSTOMER|CALLER)\s*:\s*", re.I)


def parse_transcript(raw):
    """'[13:33:14] AGENT: hi\\n\\n[13:33:19] USER: hello' -> [{'role':'agent','text':'hi'}, {'role':'caller','text':'hello'}]"""
    if isinstance(raw, list):  # already structured
        out = []
        for m in raw:
            role = str(m.get("role") or m.get("speaker") or "").lower()
            out.append({"role": "agent" if role in ("agent", "assistant", "bot") else "caller", "text": str(m.get("text") or m.get("content") or "")})
        return [m for m in out if m["text"].strip()]
    parts = LINE.split(raw or "")
    out = []
    for i in range(1, len(parts) - 1, 2):
        text = parts[i + 1].strip()
        if text:
            out.append({"role": "agent" if parts[i].upper() in ("AGENT", "ASSISTANT", "BOT") else "caller", "text": text})
    return out


def price_leaks(transcript):
    """Vaani's own AI does the talking, so we audit every agent line for a money figure after the call."""
    return [m["text"] for m in transcript if m["role"] == "agent" and c.guard_reply(m["text"])[1]]


def process(payload):
    if _store.configured():   # keep the last few raw events (for debugging the integration; no secrets inside)
        try:
            _store.set_setting("vaani_last:" + str(payload.get("event")), json.dumps(payload)[:20000])
            if payload.get("event") == "call_postprocessing":   # raw copy per call, so any call can be re-processed later
                rid = (payload.get("data") or {}).get("room_name") or payload.get("call_id") or "unknown"
                _store.set_setting("vaani_raw:" + str(rid), json.dumps(payload)[:60000])
        except Exception:
            pass
    ev = payload.get("event")
    data = payload.get("data") or payload
    room = data.get("room_name") or data.get("call_id") or payload.get("call_id") or payload.get("room_name") or "unknown"
    if ev == "call_started":
        if payload.get("phone_number") and _store.configured():
            _store.set_setting("vaani_phone:" + room, payload["phone_number"])
        return {"ok": True, "stored_phone": bool(payload.get("phone_number"))}
    if ev == "call_ended" and _store.configured():
        pid = "V-" + re.sub(r"[^A-Za-z0-9-]", "", room)[:60]
        if not _store.get(pid):   # instant placeholder; the transcript arrives a minute later and replaces it
            now = datetime.now(c.IST).isoformat()
            _store.save({"id": pid, "created_at": now, "ended_at": now, "outcome": "processing", "label": "Call finished - transcript on its way",
                         "real_call": True, "channel": "vaani-webrtc" if room.startswith(("webrtc", "room")) else "vaani-phone", "vaani_call_id": room,
                         "duration_secs": int(float(data.get("call_duration") or payload.get("call_duration") or 0)), "transcript": [], "facts": {}, "name": None,
                         "phone": None, "note": "", "first_response_secs": 1.0, "next_action": "Vaani is writing the transcript; this updates by itself."})
        return {"ok": True, "placeholder": pid}
    if ev != "call_postprocessing":
        return {"ok": True, "ignored": ev}
    transcript = parse_transcript(data.get("transcript") or data.get("transcription"))
    if not any(m["role"] == "caller" for m in transcript):
        return {"ok": True, "skipped": "no caller speech"}
    phone = data.get("phone_number") or data.get("contact_number") or payload.get("phone_number")
    if str(phone).lower() in ("web-user", "n/a", "none", ""):
        phone = None
    if not phone and _store.configured():
        phone = _store.get_setting("vaani_phone:" + room)
    lead_id = "V-" + re.sub(r"[^A-Za-z0-9-]", "", room)[:60]
    if _store.configured():
        existing = _store.get(lead_id)
        if existing and existing.get("outcome") != "processing":
            return {"ok": True, "duplicate": lead_id}
    channel = "vaani-webrtc" if room.startswith(("webrtc", "room")) else "vaani-phone"
    def when(v):
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(c.IST)
        except ValueError:
            return None
    end = when(data.get("call_ended_at")) or datetime.now(c.IST)
    dur = float(data.get("call_duration") or 0)
    if dur > 3600:          # the docs say milliseconds; live WebRTC events send seconds - accept both
        dur = dur / 1000.0
    start = when(data.get("call_started_at")) or when(data.get("picked_up_at")) or (end - timedelta(seconds=dur or 60))
    facts, usage = c.extract_facts(transcript, None, end)
    leaks = price_leaks(transcript)
    body = {"lead_id": lead_id, "transcript": transcript, "facts": facts, "phone": phone or ("browser call (WebRTC)" if channel == "vaani-webrtc" else "unknown number"),
            "started_at": start.isoformat(), "ended_at": end.isoformat(),
            "ended_by": "agent" if "disconnect" in str(data.get("end_reason", "")).lower() or "ended" in str(data.get("end_reason", "")).lower() else "caller",
            "usage": usage, "cost_inr": c.cost_inr(usage), "model": "vaani voice agent + " + c.model_name(),
            "price_blocked": len(leaks), "first_response_secs": 1.0, "demo": False, "strict_qual": True}
    out = finalize.process_finalize(body)
    lead = out["lead"]
    extra = {"channel": channel, "vaani_call_id": room, "recording_url": data.get("recording_url"), "vaani_summary": data.get("summary"),
             "vaani_entities": data.get("entities"), "vaani_quality": data.get("conversation_quality"), "vaani_end_reason": data.get("end_reason"), "vaani_dispositions": data.get("dispositions"), "real_call": True,
             "duration_secs": int(dur) if dur else lead.get("duration_secs")}
    if leaks:
        extra["price_leak"] = leaks[:3]
        c.send_telegram("⚠ PRICE RULE BROKEN on call %s. The voice agent said: \"%s\". Review the agent prompt." % (room, leaks[0][:200]), "alert", urgent=True)
    lead.update(extra)
    if _store.configured():
        try:
            _store.save(lead)
        except Exception:
            pass
    return {"ok": True, "lead_id": lead["id"], "outcome": lead["outcome"], "price_leaks": len(leaks)}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        want = os.environ.get("VAANI_WEBHOOK_SECRET")
        if want and ("key=" + want) not in self.path:
            return send(self, {"ok": False}, 401)
        try:
            send(self, process(read_json(self)))
        except Exception as e:
            send(self, {"ok": False, "error": str(e)[:200]}, 200)  # 200 so Vaani does not retry forever

    def log_message(self, *a):
        pass
