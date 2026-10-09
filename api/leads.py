"""GET /api/leads -> {mode, leads}. In 'local' mode the dashboard reads the browser's own saved calls."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler
from _http import send
import _store


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not _store.configured():
            return send(self, {"mode": "local", "leads": []})
        want = os.environ.get("DASHBOARD_KEY")
        if not want:
            return send(self, {"mode": "locked", "leads": [], "error": "Set DASHBOARD_KEY on Vercel to protect the shared dashboard."})
        if self.headers.get("x-dashboard-key") != want:
            return send(self, {"mode": "locked", "leads": [], "error": "Wrong or missing dashboard key."}, 401)
        try:
            send(self, {"mode": "shared", "leads": _store.list_leads()})
        except Exception as e:
            send(self, {"mode": "local", "leads": [], "error": str(e)[:160]})

    def log_message(self, *a):
        pass
