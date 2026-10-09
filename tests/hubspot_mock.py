"""Fake HubSpot to prove the sync sends correctly shaped requests. Run: python3 -I tests/hubspot_mock.py"""
import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))
LOG, CONTACTS = [], {}

class H(BaseHTTPRequestHandler):
    def _b(self):
        n = int(self.headers.get("content-length") or 0); return json.loads(self.rfile.read(n) or b"{}")
    def _r(self, o, c=200):
        b = json.dumps(o).encode(); self.send_response(c); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        b = self._b(); LOG.append(("POST", self.path, b, self.headers.get("Authorization")))
        if self.path.endswith("/contacts/search"):
            v = b["filterGroups"][0]["filters"][0]["value"]; return self._r({"results": [{"id": CONTACTS[v]}] if v in CONTACTS else []})
        if self.path.endswith("/contacts"):
            CONTACTS[b["properties"]["phone"]] = "101"; return self._r({"id": "101"}, 201)
        return self._r({"id": "9%d" % len(LOG)}, 201)
    def do_PATCH(self):
        LOG.append(("PATCH", self.path, self._b(), None)); self._r({"id": "101"})
    def log_message(self, *a): pass

srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ.update(HUBSPOT_TOKEN="test-token", HUBSPOT_BASE="http://127.0.0.1:%d" % srv.server_port)
import _hubspot as h
lead = {"outcome": "qualified", "label": "Qualified - sent to designer", "phone": "+91 98765 43210", "name": "Priya Kulkarni", "note": "HOT LEAD\nline2", "facts": {"project_type": "full_home", "location_text": "Kothrud"}}
r1 = h.sync_lead(lead); r2 = h.sync_lead(dict(lead, outcome="escalated")); r3 = h.sync_lead(dict(lead, outcome="closed"))
print("first call :", r1); print("repeat call:", r2); print("closed     :", r3["error"])
paths = [(m, p.split("/crm/v3/objects/")[1]) for m, p, _, _ in LOG]; print(paths)
deal = [b for m, p, b, _ in LOG if p.endswith("/deals")][0]
assert r1["ok"] and r1["deal_id"] and r1["note_id"] and r2["ok"] and r2["contact_id"] == "101" and r2["deal_id"] is None and not r3["ok"]
assert deal["associations"][0]["types"][0]["associationTypeId"] == 3 and deal["properties"]["dealstage"] == "appointmentscheduled"
assert [x for x in LOG if x[3]][0][3] == "Bearer test-token" and sum(1 for m, p, *_ in LOG if m == "POST" and p.endswith("/contacts")) == 1
print("OK: contact created once, matched on repeat call, note added, deal only for qualified, closed never sent")
