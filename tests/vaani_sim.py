"""Simulates Vaani webhooks against api/vaani.py (no keys, no real systems). Run: python3 -I tests/vaani_sim.py"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(ROOT, "api"))
for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "DATABASE_URL", "TELEGRAM_BOT_TOKEN", "HUBSPOT_TOKEN", "TELEGRAM_CHAT_ID"): os.environ.pop(k, None)
import vaani, _store, finalize, _core as c
MEM, LEADS, TG = {}, [], []
_store.configured = lambda: True; _store.get_setting = lambda k: MEM.get(k); _store.set_setting = lambda k, v: MEM.__setitem__(k, v); _store.save = lambda l: LEADS.append(l); _store.get = lambda i: next((l for l in LEADS if l['id'] == i), None)
c.send_telegram = lambda t, i, urgent=False: TG.append(t) or {"sent": False}
T = ("[13:33:14] AGENT: Namaste, thank you for calling Aangan Studio. How can I help you today?\n\n[13:33:19] USER: Hi, I have a 3BHK in Kothrud and want the whole thing redone with execution. How much per sq ft?\n\n"
     "[13:33:25] AGENT: Pricing depends on the site, the materials you choose, and the scope. When would you need it completed?\n\n[13:33:31] USER: By March, no rush. About 1400 sq ft, a bare builder flat.\n\n"
     "[13:33:40] AGENT: May I have your name?\n\n[13:33:44] USER: I'm Priya Kulkarni, my husband and I own it. Weekends work best.\n\n[13:33:50] AGENT: Thank you. I've passed everything to our design team. Goodbye.")
print(vaani.process({"event": "call_started", "room_name": "outbound-1-abc", "status": "dialing", "phone_number": "+919876543210"}))
r = vaani.process({"event": "call_postprocessing", "call_id": "outbound-1-abc", "data": {"room_name": "outbound-1-abc", "call_duration": 55150.0, "end_reason": "Call ended", "summary": "x", "transcript": T}})
print(r); L = LEADS[-1]
assert r["outcome"] == "qualified" and L["phone"] == "+919876543210" and L["channel"] == "vaani-phone" and r["price_leaks"] == 0
tr = vaani.parse_transcript(T); assert tr[0]["role"] == "agent" and tr[1]["role"] == "caller" and len(tr) == 7
# a price leak by the voice agent is caught and alerted
r2 = vaani.process({"event": "call_postprocessing", "data": {"room_name": "r2", "call_duration": 30000, "transcript": "AGENT: Hello.\n\n USER: I have a flat in Baner, what's your rate?\n\n AGENT: Our rates start at 1800 per sq ft."}})
assert r2["price_leaks"] == 1 and any("PRICE RULE BROKEN" in t for t in TG); print(r2, "| alert sent:", TG[-1][:60])
# Nashik caller -> closed; complaint -> escalated
assert vaani.process({"event": "call_postprocessing", "data": {"room_name": "r3", "transcript": "AGENT: Hi.\n\n USER: I'm in Nashik, can you do my home office?\n\n AGENT: We only work in Pune."}})["outcome"] == "closed"
assert vaani.process({"event": "call_postprocessing", "data": {"room_name": "r4", "transcript": "AGENT: Hi.\n\n USER: My project has been going for three months and my designer hasn't replied. Not acceptable, I want someone senior."}})["outcome"] == "escalated"
assert vaani.process({"event": "call_ended", "room_name": "r5", "call_duration": 12})["ignored"] == "call_ended"
# same call delivered twice -> stored once
again = vaani.process({"event": "call_postprocessing", "call_id": "outbound-1-abc", "data": {"room_name": "outbound-1-abc", "call_duration": 55150.0, "transcript": T}})
assert again.get("duplicate"), again
# a browser (WebRTC) call is labelled as such and gets a next action
w = vaani.process({"event": "call_postprocessing", "data": {"room_name": "webrtc-1-x", "call_duration": 40000, "transcript": T}})
Lw = [l for l in LEADS if l["id"] == w["lead_id"]][-1]
assert Lw["channel"] == "vaani-webrtc" and Lw["real_call"] and Lw["next_action"].startswith("Designer calls back"), Lw["next_action"]
# real WebRTC payload shape (seconds, web-user, ISO times)
real = {"event": "call_postprocessing", "call_id": "webrtc-9-z", "data": {"room_name": "webrtc-9-z", "phone_number": "web-user", "call_duration": 29.99,
        "call_started_at": "2026-10-10T09:16:52.79+00:00", "call_ended_at": "2026-10-10T09:17:22.75+00:00", "conversation_quality": {"overall_quality": 7}, "transcript": T.replace("\n\n", "\n")}}
rw = vaani.process(real); Lr = [l for l in LEADS if l["id"] == rw["lead_id"]][-1]
assert Lr["duration_secs"] == 29 and Lr["phone"] == "browser call (WebRTC)" and Lr["vaani_quality"]["overall_quality"] == 7, (Lr["duration_secs"], Lr["phone"])
print("dedupe + WebRTC labelling + next action + real payload shape OK")
print("ALL VAANI WEBHOOK TESTS PASSED")
