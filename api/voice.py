"""POST /api/voice - the REAL phone path (Twilio-compatible webhook).

How a real call flows once a phone number is connected:
  caller dials -> Twilio answers and POSTs here -> we reply with TwiML: <Say> the greeting, <Gather input="speech">
  -> Twilio transcribes what the caller says and POSTs it here as SpeechResult -> same brain as the web demo
  (extract facts -> rules -> reply) -> we <Say> the reply and gather again -> ... -> <Hangup>.
  When the line closes, Twilio calls /api/voice?status=1 so a dropped call still becomes a call-back lead.
Call state (transcript, facts) is kept in Neon between turns. Set TWILIO_AUTH_TOKEN to verify requests really come from Twilio.
This is the only thing that changes when the browser microphone is replaced by a phone number."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import base64
import hashlib
import hmac
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from xml.sax.saxutils import escape
import _core as c
import _store
import turn
import finalize

VOICE = os.environ.get("TWILIO_VOICE", "Polly.Aditi")      # bilingual Indian English / Hindi voice
LANG = os.environ.get("TWILIO_LANG", "en-IN")


def valid_signature(url, params, signature):
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not token:
        return True   # not enforced until the token is set; set it before going live
    data = url + "".join(k + params[k] for k in sorted(params))
    mac = base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(mac, signature or "")


def say(text):
    return '<Say voice="%s" language="%s">%s</Say>' % (VOICE, LANG, escape(text))


def gather(text, action):
    return ('<?xml version="1.0" encoding="UTF-8"?><Response><Gather input="speech" language="%s" speechTimeout="auto" action="%s" method="POST">%s</Gather>'
            '<Redirect method="POST">%s</Redirect></Response>') % (LANG, escape(action), say(text), escape(action))


def bye(text):
    return '<?xml version="1.0" encoding="UTF-8"?><Response>%s<Hangup/></Response>' % say(text)


def load(sid):
    raw = _store.get_setting("call:" + sid)
    return json.loads(raw) if raw else None


def save(sid, st):
    _store.set_setting("call:" + sid, json.dumps(st))


def end_call(sid, st, by):
    body = {"transcript": st["transcript"], "facts": st["facts"], "phone": st.get("phone"), "started_at": st["started_at"],
            "ended_at": datetime.now(c.IST).isoformat(), "ended_by": by, "usage": st["usage"], "cost_inr": st["cost"],
            "model": c.model_name(), "price_blocked": st["blocked"], "first_response_secs": 1.0, "demo": False}
    out = finalize.process_finalize(body)
    try:
        _store.delete_setting("call:" + sid)
    except Exception:
        pass
    return out


def handle(params, action_url, status=False):
    """Pure function: Twilio form params in, TwiML (or '') out. Easy to test without a phone."""
    sid = params.get("CallSid", "unknown")
    st = load(sid)
    if status:   # call closed by Twilio / caller hung up
        if st and any(m["role"] == "caller" for m in st["transcript"]):
            end_call(sid, st, "caller")
        elif st:
            _store.delete_setting("call:" + sid)
        return ""
    speech = (params.get("SpeechResult") or "").strip()
    if not st:
        st = {"transcript": [{"role": "agent", "text": c.GREETING}], "facts": None, "asked": {}, "usage": {"input": 0, "output": 0},
              "cost": 0.0, "blocked": 0, "started_at": datetime.now(c.IST).isoformat(), "phone": params.get("From"), "silent": 0}
        save(sid, st)
        return gather(c.GREETING, action_url)
    if not speech:                      # silence
        st["silent"] += 1
        if st["silent"] >= 2:
            end_call(sid, st, "caller")
            return bye("I didn't hear anything, so I'll let you go. Please call us again anytime. Goodbye.")
        save(sid, st)
        return gather("Sorry, I didn't catch that. Could you say that again?", action_url)
    st["silent"] = 0
    st["transcript"].append({"role": "caller", "text": speech})
    r = turn.process_turn({"transcript": st["transcript"], "facts": st["facts"], "asked": st["asked"]})
    st["facts"], st["asked"] = r["facts"], r["asked"]
    st["usage"]["input"] += r["usage"]["input"]; st["usage"]["output"] += r["usage"]["output"]
    st["cost"] += r["cost_inr"]; st["blocked"] += 1 if r["price_blocked"] else 0
    st["transcript"].append({"role": "agent", "text": r["reply"]})
    if r["done"]:
        end_call(sid, st, "agent")
        return bye(r["reply"])
    save(sid, st)
    return gather(r["reply"], action_url)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        params = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode() if n else "", keep_blank_values=True).items()}
        host = self.headers.get("x-forwarded-host") or self.headers.get("host")
        url = "https://%s/api/voice" % host + ("?status=1" if "status=1" in self.path else "")
        if not valid_signature(url, params, self.headers.get("x-twilio-signature")):
            self.send_response(403); self.end_headers(); return
        try:
            body = handle(params, "https://%s/api/voice" % host, status="status=1" in self.path).encode()
        except Exception:
            body = ('<?xml version="1.0" encoding="UTF-8"?><Response>' + say("Sorry, something went wrong on our side. Our team will call you back shortly. Goodbye.") + "<Hangup/></Response>").encode()
        self.send_response(200); self.send_header("content-type", "text/xml"); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass
