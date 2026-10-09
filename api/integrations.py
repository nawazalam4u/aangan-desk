"""/api/integrations
GET  -> which systems are connected (no secrets).
POST {check: ai|db|telegram|hubspot} with header x-dashboard-key -> runs a real test of that connection."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler
from datetime import datetime
from _http import read_json, send
import _core as c
import _store
import _hubspot


def status():
    return {"ai": {"on": c.provider() != "none", "detail": c.model_name()},
            "db": {"on": _store.configured(), "detail": "Neon Postgres" if _store.configured() else "browser only"},
            "telegram": {"on": c.telegram_configured(), "detail": "designers' chat registered" if c.telegram_configured() else "not connected"},
            "hubspot": {"on": _hubspot.configured(), "detail": "CRM sync on" if _hubspot.configured() else "not connected",
                        "portal": os.environ.get("HUBSPOT_PORTAL_ID")}}


def run_check(name):
    if name == "ai":
        txt, u = c.llm("Reply with exactly: OK", "ping", 10)
        return "AI answered \"%s\" using %s (%d tokens)" % (txt.strip()[:12], c.model_name(), u["input"] + u["output"])
    if name == "db":
        n = len(_store.list_leads(1000))
        return "Neon database reachable. %d calls stored." % n
    if name == "telegram":
        r = c.send_telegram("\u2705 Aangan Desk test message, sent %s. Handoff notes will arrive in this chat." % datetime.now(c.IST).strftime("%d %b %I:%M %p"), "test", urgent=True)
        if not r.get("sent"):
            raise RuntimeError(r.get("reason", "Telegram did not accept the message"))
        return "Test message delivered to the registered Telegram chat."
    if name == "hubspot":
        if not _hubspot.configured():
            raise RuntimeError("HUBSPOT_TOKEN is not set yet")
        r = _hubspot._req("GET", "/crm/v3/objects/contacts?limit=1")
        return "HubSpot reachable and the token is accepted (contacts readable)."
    raise RuntimeError("unknown check")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        send(self, status())

    def do_POST(self):
        want = os.environ.get("DASHBOARD_KEY")
        if not want or self.headers.get("x-dashboard-key") != want:
            return send(self, {"ok": False, "message": "Enter the dashboard key first."}, 401)
        try:
            send(self, {"ok": True, "message": run_check(read_json(self).get("check"))})
        except Exception as e:
            send(self, {"ok": False, "message": str(e)[:240]})

    def log_message(self, *a):
        pass
