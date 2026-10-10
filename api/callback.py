"""POST /api/callback {lead_id} (header x-dashboard-key) - ask the Vaani agent to CALL the customer back.
Used for dropped calls and call-back leads. Only people who already enquired are called (consent)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler
from _http import read_json, send
import _store


def dispatch(phone, name):
    req = urllib.request.Request("https://api.vaanivoice.ai/api/trigger-call/", method="POST",
                                 data=json.dumps({"agent_id": os.environ["VAANI_AGENT_ID"], "medium": "telephony",
                                                  "contact_number": phone, "name": name or "there", "metadata": {}}).encode(),
                                 headers={"X-API-Key": os.environ["VAANI_API_KEY"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError("Vaani %s: %s" % (e.code, e.read().decode()[:200]))


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        want = os.environ.get("DASHBOARD_KEY")
        if not want or self.headers.get("x-dashboard-key") != want:
            return send(self, {"ok": False, "message": "Dashboard key needed."}, 401)
        if not (os.environ.get("VAANI_API_KEY") and os.environ.get("VAANI_AGENT_ID")):
            return send(self, {"ok": False, "message": "Vaani is not connected yet (VAANI_API_KEY / VAANI_AGENT_ID)."})
        b = read_json(self)
        lead = _store.get(b.get("lead_id", "")) if _store.configured() else None
        phone = re.sub(r"[^\d+]", "", (lead or {}).get("phone") or b.get("phone") or "")
        if not re.fullmatch(r"\+\d{10,15}", phone):
            return send(self, {"ok": False, "message": "No valid phone number (E.164, e.g. +919876543210) on this lead."})
        try:
            r = dispatch(phone, (lead or {}).get("name"))
            if lead:
                lead.setdefault("callbacks", []).append({"phone": phone, "vaani": r})
                _store.save(lead)
            send(self, {"ok": True, "message": "Calling %s now." % phone, "vaani": r})
        except Exception as e:
            send(self, {"ok": False, "message": str(e)[:240]})

    def log_message(self, *a):
        pass
