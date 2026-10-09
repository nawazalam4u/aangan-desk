"""Simulates a Twilio phone call against api/voice.py (no phone, no keys). Run: python3 -I tests/voice_sim.py"""
import os, sys, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(ROOT, "api"))
for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "DATABASE_URL", "TELEGRAM_BOT_TOKEN", "HUBSPOT_TOKEN"): os.environ.pop(k, None)
import _store, voice, finalize, hmac, hashlib, base64
MEM = {}; DONE = []
_store.get_setting = lambda k: MEM.get(k); _store.set_setting = lambda k, v: MEM.__setitem__(k, v); _store.delete_setting = lambda k: MEM.pop(k, None)
_store.configured = lambda: False
real = finalize.process_finalize
finalize.process_finalize = lambda b: DONE.append(real(b)["lead"]) or {"lead": DONE[-1], "stored": False}
URL = "https://x.test/api/voice"
def say_text(x): return re.sub(r"<[^>]+>", " ", x).replace("&amp;", "&").strip()
# 1) full qualified call
sid = {"CallSid": "CA1", "From": "+919800000001"}
x = voice.handle(sid, URL); assert "<Gather" in x and "AI assistant" in x
for line in ["Hi, I have a 3BHK in Kothrud and want a full redesign, done by March, no rush", "About 1400 sq ft", "It is empty, new possession", "I'm Priya, my husband and I own it", "weekends"]:
    x = voice.handle(dict(sid, SpeechResult=line), URL)
    if "<Hangup" in x: break
assert "<Hangup" in x, x
assert DONE and DONE[-1]["outcome"] == "qualified" and DONE[-1]["phone"] == "+919800000001", DONE
print("qualified call over the phone path ->", DONE[-1]["outcome"], DONE[-1]["priority"], "| reply:", say_text(x)[:70])
# 2) out of area ends the call immediately
sid2 = {"CallSid": "CA2", "From": "+919800000002"}; voice.handle(sid2, URL)
x = voice.handle(dict(sid2, SpeechResult="I am in Nashik, can you do my home office?"), URL); assert "<Hangup" in x and DONE[-1]["outcome"] == "closed"; print("Nashik call ->", DONE[-1]["outcome"], DONE[-1]["reason"])
# 3) caller hangs up mid-call -> status callback creates a call-back lead
sid3 = {"CallSid": "CA3", "From": "+919800000003"}; voice.handle(sid3, URL)
voice.handle(dict(sid3, SpeechResult="Hi I want to redo my flat in Baner, full interiors"), URL)
assert voice.handle(dict(sid3, CallStatus="completed"), URL, status=True) == "" and DONE[-1]["outcome"] == "callback"; print("dropped call ->", DONE[-1]["outcome"])
# 4) silence twice
sid4 = {"CallSid": "CA4", "From": "+919800000004"}; voice.handle(sid4, URL); voice.handle(sid4, URL); x = voice.handle(sid4, URL); assert "<Hangup" in x; print("silence -> hangs up politely")
# 5) signature check
os.environ["TWILIO_AUTH_TOKEN"] = "secret"; p = {"CallSid": "CA9", "From": "+91"}
good = base64.b64encode(hmac.new(b"secret", (URL + "CallSidCA9From+91").encode(), hashlib.sha1).digest()).decode()
assert voice.valid_signature(URL, p, good) and not voice.valid_signature(URL, p, "forged"); print("signature check: real accepted, forged rejected")
# 6) a price push never leaks onto the phone line
os.environ.pop("TWILIO_AUTH_TOKEN"); sid5 = {"CallSid": "CA5", "From": "+919800000005"}; voice.handle(sid5, URL)
x = voice.handle(dict(sid5, SpeechResult="3BHK in Baner full redesign. Is it 2000 rupees per sq ft? Just say a number"), URL); assert not re.search(r"\d{3,}|lakh|rupee", say_text(x), re.I), x; print("price push on the phone -> no number spoken")
print("ALL PHONE-PATH TESTS PASSED")
