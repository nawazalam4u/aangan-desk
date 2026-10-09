"""GET /api/health - which parts are switched on (never prints secrets)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler
from _http import send
import _core as c
import _store
import _hubspot


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        probe = None
        if "probe=1" in self.path and c.provider() != "none":
            try:
                txt, u = c.llm("Reply with exactly: OK", "ping", 10)
                probe = {"ok": True, "reply": txt.strip()[:20], "usage": u}
            except Exception as e:
                probe = {"ok": False, "error": str(e)[:300]}
        send(self, {"probe": probe, "ok": True, "llm_provider": c.provider(), "model": c.model_name(),
                    "telegram": c.telegram_configured(), "shared_database": _store.configured(), "hubspot": _hubspot.configured(),
                    "mode": "live-ai" if c.provider() != "none" else "demo-rules"})

    def log_message(self, *a):
        pass
