"""POST /api/cal?key=<CAL_WEBHOOK_SECRET> - Cal.com booking webhook.
When a consultation is booked (by the designer from the dashboard/Telegram link, or by the Vaani agent), the lead is
marked "consultation booked" on the dashboard and a note is added to its HubSpot contact. Cal.com's own HubSpot app
also logs the meeting in HubSpot."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
from http.server import BaseHTTPRequestHandler
from _http import read_json, send
import _store
import _hubspot
import _core as c


def booking_url(lead):
    base = os.environ.get("CAL_BOOKING_URL")
    if not base:
        return None
    from urllib.parse import urlencode
    f = lead.get("facts") or {}
    q = {"name": lead.get("name") or "", "notes": (lead.get("vaani_summary") or lead.get("next_action") or "")[:400], "metadata[lead_id]": lead["id"]}
    if f.get("location_text"):
        q["location"] = f["location_text"]
    return base + "?" + urlencode({k: v for k, v in q.items() if v})


def process(p):
    ev = p.get("triggerEvent") or p.get("event")
    b = p.get("payload") or {}
    lead_id = (b.get("metadata") or {}).get("lead_id") or (b.get("responses") or {}).get("lead_id", {}).get("value")
    att = (b.get("attendees") or [{}])[0]
    if not lead_id and _store.configured():   # match by name if the booking was not made from our link
        name = (att.get("name") or "").lower()
        lead_id = next((l["id"] for l in _store.list_leads() if name and (l.get("name") or "").lower() == name), None)
    if not lead_id or not _store.configured():
        return {"ok": True, "matched": False, "event": ev}
    lead = _store.get(lead_id)
    if not lead:
        return {"ok": True, "matched": False}
    if ev == "BOOKING_CANCELLED":
        lead["booking"] = dict(lead.get("booking") or {}, status="cancelled")
    else:
        lead["booking"] = {"status": "booked", "start": b.get("startTime"), "end": b.get("endTime"), "uid": b.get("uid"),
                           "title": b.get("title"), "attendee": att.get("name"), "email": att.get("email")}
        hs = lead.get("hubspot") or {}
        if _hubspot.configured() and hs.get("contact_id"):
            try:
                _hubspot._req("POST", "/crm/v3/objects/notes", {"properties": {"hs_note_body": "[Aangan Desk] Consultation booked on Cal.com for %s." % b.get("startTime"),
                                                                               "hs_timestamp": int(time.time() * 1000)}, "associations": _hubspot._assoc(hs["contact_id"], 202)})
                if hs.get("deal_id"):
                    _hubspot._req("PATCH", "/crm/v3/objects/deals/%s" % hs["deal_id"], {"properties": {"dealstage": "qualifiedtobuy"}})
            except Exception as e:
                lead["booking"]["hubspot_error"] = str(e)[:120]
        c.send_telegram("\U0001f4c5 Consultation booked: %s on %s." % (lead.get("name") or att.get("name") or "lead", b.get("startTime")), lead_id, urgent=True)
    _store.save(lead)
    return {"ok": True, "matched": lead_id, "status": lead["booking"]["status"]}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        want = os.environ.get("CAL_WEBHOOK_SECRET")
        if want and ("key=" + want) not in self.path:
            return send(self, {"ok": False}, 401)
        try:
            send(self, process(read_json(self)))
        except Exception as e:
            send(self, {"ok": False, "error": str(e)[:200]})

    def log_message(self, *a):
        pass
