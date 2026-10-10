"""POST /api/live (header x-dashboard-key) - start a LIVE call with the real Vaani voice agent.
  {"mode": "webrtc"}                         -> in-browser voice call; returns LiveKit token + server URL + live captions URL
  {"mode": "phone", "number": "+91...", "name": "..."} -> the agent dials that number now
Protected by the dashboard key because every live minute is billed by Vaani."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler
from _http import read_json, send


def vaani(body):
    body = dict(body, agent_id=os.environ["VAANI_AGENT_ID"])
    req = urllib.request.Request("https://api.vaanivoice.ai/api/trigger-call/", method="POST", data=json.dumps(body).encode(),
                                 headers={"X-API-Key": os.environ["VAANI_API_KEY"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError("Vaani said %s: %s" % (e.code, e.read().decode()[:220]))


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        want = os.environ.get("DASHBOARD_KEY")
        if not want or self.headers.get("x-dashboard-key") != want:
            return send(self, {"ok": False, "message": "Enter the access key first (same as the dashboard key)."}, 401)
        if not (os.environ.get("VAANI_API_KEY") and os.environ.get("VAANI_AGENT_ID")):
            return send(self, {"ok": False, "message": "The Vaani agent is not connected."})
        b = read_json(self)
        try:
            if b.get("mode") == "phone":
                num = re.sub(r"[^\d+]", "", str(b.get("number", "")))
                if not re.fullmatch(r"\+\d{10,15}", num):
                    return send(self, {"ok": False, "message": "Use the full number with country code, e.g. +919876543210."})
                r = vaani({"medium": "telephony", "contact_number": num, "name": (str(b.get("name") or "there"))[:60], "metadata": {}})
                return send(self, {"ok": True, "mode": "phone", "message": "The AI agent is calling %s now." % num, "vaani": r})
            r = vaani({"medium": "webrtc", "metadata": {}, "primary_language": "en", "secondary_language": "hi", "voice_gender": "female",
                       "welcome_interruptible": True})
            url = r.get("connection_url", "")
            send(self, {"ok": True, "mode": "webrtc", "token": r.get("token"), "room_name": r.get("room_name"),
                        "server_url": url.replace("https://", "wss://").replace("http://", "ws://"), "live_captions_url": r.get("live_captions_url")})
        except Exception as e:
            send(self, {"ok": False, "message": str(e)[:240]})

    def log_message(self, *a):
        pass
