"""Optional HubSpot CRM sync. Off unless HUBSPOT_TOKEN is set (a HubSpot Private App token).
For each qualified / call-back / escalated lead it: finds or creates the Contact (matched on phone),
adds the handoff note to the contact timeline, and (qualified + call-back only) opens a Deal linked to the contact.
The app never depends on this: if HubSpot is down or mis-set, the call, Telegram note and dashboard still work."""
import json
import os
import re
import time
import urllib.request
import urllib.error

BASE = os.environ.get("HUBSPOT_BASE", "https://api.hubapi.com")
ASSOC_DEAL_TO_CONTACT = 3      # HubSpot-defined association type ids
ASSOC_NOTE_TO_CONTACT = 202


def configured():
    return bool(os.environ.get("HUBSPOT_TOKEN"))


def _req(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + os.environ["HUBSPOT_TOKEN"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError("HubSpot %s %s: %s" % (e.code, path, e.read().decode()[:160]))


def _assoc(to_id, type_id):
    return [{"to": {"id": str(to_id)}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": type_id}]}]


def _phone(p):
    d = re.sub(r"\D", "", p or "")
    return ("+91" + d[-10:]) if len(d) >= 10 else None


def sync_lead(lead):
    """Returns {ok, contact_id, deal_id, note_id, error}. Never raises."""
    out = {"ok": False, "contact_id": None, "deal_id": None, "note_id": None, "error": None}
    if lead.get("outcome") not in ("qualified", "callback", "escalated"):
        out["error"] = "closed leads are not sent to the CRM"
        return out
    try:
        f = lead.get("facts") or {}
        phone = _phone(lead.get("phone"))
        first, _, last = (lead.get("name") or "Unknown caller").partition(" ")
        props = {"firstname": first, "lastname": last or "(phone enquiry)", "lifecyclestage": "lead", "hs_lead_status": "NEW"}
        if phone:
            props["phone"] = phone
        if f.get("location_text"):
            props["city"] = "Pune" if "pune" in f["location_text"].lower() else f["location_text"]
        cid = None
        if phone:
            res = _req("POST", "/crm/v3/objects/contacts/search", {"filterGroups": [{"filters": [{"propertyName": "phone", "operator": "EQ", "value": phone}]}], "limit": 1})
            if res.get("results"):
                cid = res["results"][0]["id"]
                _req("PATCH", "/crm/v3/objects/contacts/%s" % cid, {"properties": {k: v for k, v in props.items() if k not in ("lifecyclestage", "hs_lead_status")}})
        if not cid:
            cid = _req("POST", "/crm/v3/objects/contacts", {"properties": props})["id"]
        out["contact_id"] = cid
        note = "[Aangan Desk] %s\n\n%s" % (lead.get("label", ""), lead.get("note", ""))
        out["note_id"] = _req("POST", "/crm/v3/objects/notes", {"properties": {"hs_note_body": note.replace("\n", "<br>"), "hs_timestamp": int(time.time() * 1000)},
                                                              "associations": _assoc(cid, ASSOC_NOTE_TO_CONTACT)}).get("id")
        if lead["outcome"] in ("qualified", "callback"):
            name = "%s - %s, %s" % (lead.get("name") or "Phone enquiry", (f.get("project_type") or "project").replace("_", " "), f.get("location_text") or "Pune")
            out["deal_id"] = _req("POST", "/crm/v3/objects/deals", {
                "properties": {"dealname": name, "pipeline": os.environ.get("HUBSPOT_PIPELINE", "default"),
                               "dealstage": os.environ.get("HUBSPOT_DEAL_STAGE", "appointmentscheduled")},
                "associations": _assoc(cid, ASSOC_DEAL_TO_CONTACT)}).get("id")
        out["ok"] = True
    except Exception as e:
        out["error"] = str(e)[:240]
    return out
