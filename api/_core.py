"""Aangan Desk core: the brain of the phone-enquiry agent.

Design rule: the AI *talks and extracts*; plain code *decides*.
  1. extract_facts()  -> turns the call transcript into structured facts (LLM, or regex fallback)
  2. evaluate()       -> applies Nikhil's 5-criteria rubric (qualified.md) in code
  3. directive        -> tells the speaker what to do next (ask X / decline / escalate / close)
  4. speak()          -> the LLM words the reply (or a template if no key)
  5. guard_reply()    -> last line of defence: no price can ever leave the system
Rules live in code (not only in a prompt) because pricing and qualification are judgment calls
Nikhil owns, and code can be tested against the 40 real September enquiries.
"""
import json
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# --------------------------------------------------------------------------------------
# Config (all overridable with environment variables on Vercel)
# --------------------------------------------------------------------------------------
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
GEMINI_MODELS = [m.strip() for m in os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite,gemini-3.5-flash").split(",") if m.strip()]
GEMINI_MODEL = GEMINI_MODELS[0]  # gemini-2.5-flash was retired for new users; lite is fast (~1s) and cheap
LAST_ERROR = {"msg": None}
LAST_MODEL = {"name": None}
USD_INR = float(os.environ.get("USD_INR", "88"))  # editable assumption

# USD per 1M tokens (input, output). Haiku 5.5 from Anthropic's published table (<=100K prompts).
# Gemini prices are the paid-tier list price; the free tier costs 0 but we show list price for planning.
PRICES = {
    "anthropic": (0.10, 0.50),
    "gemini": (0.25, 1.50),  # Gemini 3.1 Flash-Lite list price per third-party trackers; verify at ai.google.dev/pricing
}

OFFICE_OPEN, OFFICE_CLOSE = 10, 19  # 10am-7pm front desk
MIN_LEAD_WEEKS = 6          # services.md: cannot begin execution if it must be ready in < 6 weeks
TIGHT_WEEKS = 12            # design 3-4 wks + execution 8-16 wks: flag anything tighter for the designer
COMMERCIAL_MAX_SQFT = 3000  # services.md
COMMERCIAL_MIN_SQFT = 500   # NOT in services.md - only stated by front desk in T18. Flagged for Nikhil.
ROOM_FLOOR_LAKH = 3.5       # pricing.md: single room redesign starts at 3.5 lakh (internal only)
APPROVED_PRICING_LINE = (
    "Pricing depends on the site, the materials you choose, and the scope — your designer will "
    "walk you through it in detail at the consultation. I can book that for you right now if you'd like."
)

AREAS_IN = [
    "pune", "pcmc", "kothrud", "baner", "aundh", "wakad", "koregaon park", "kalyani nagar", "viman nagar",
    "hadapsar", "magarpatta", "nibm", "kondhwa", "undri", "shivane", "warje", "erandwane", "deccan",
    "pimpri", "chinchwad", "pimple saudagar", "pimple nilakh", "ravet", "hinjewadi",
    # adjoining Pune localities the studio already serves in the transcripts
    "kharadi", "nanded", "bavdhan", "balewadi", "pashan", "yerwada", "wanowrie", "mundhwa", "katraj",
    "dhanori", "sus ", "camp", "bund garden", "sadashiv peth", "shivajinagar", "lohegaon", "wagholi",
]
AREAS_OUT = [
    "talegaon", "lonavala", "lonavla", "nashik", "mumbai", "navi mumbai", "thane", "nagpur", "kolhapur",
    "satara", "solapur", "aurangabad", "bangalore", "bengaluru", "delhi", "hyderabad", "goa", "alibag",
    "khopoli", "chennai", "kolkata", "ahmedabad", "indore", "surat",
]

OUT_OF_SCOPE_WORDS = ["restaurant", "hotel", "resort", "retail", "shop ", "showroom", "gym", "fitness", "cafe", "café", "salon", "spa "]

# --------------------------------------------------------------------------------------
# Facts schema
# --------------------------------------------------------------------------------------
EMPTY_FACTS = {
    "caller_name": None,
    "project_type": None,        # full_home | partial_home | single_room | office | advice_only | out_of_scope | other
    "scope_text": None,          # rooms / what they want, in their words
    "wants_execution": None,     # true | false | null   (false = just ideas/advice)
    "just_exploring": None,      # true if "just exploring / early stage / maybe later"
    "location_text": None,
    "area_sqft": None,           # number (carpet)
    "property_state": None,      # bare / new possession / lived-in / rented ...
    "timeline_status": None,     # hard_deadline | flexible | start_only | unknown
    "ready_by_weeks": None,      # number, only for hard_deadline (weeks from today)
    "timeline_text": None,
    "budget_min_lakh": None,
    "budget_max_lakh": None,
    "decision_maker": None,      # self | authorised | researching_for_others | unknown
    "referral_source": None,
    "preferred_slot": None,
    "asked_price": None,         # true if caller asked for a price/ballpark at any point
    "existing_client_complaint": None,
    "wants_human": None,
    "language": None,
    "notes": None,
}


def clean_facts(f):
    out = dict(EMPTY_FACTS)
    if isinstance(f, dict):
        for k in EMPTY_FACTS:
            if k in f and f[k] not in ("", "null", "None"):
                out[k] = f[k]
    for k in ("area_sqft", "ready_by_weeks", "budget_min_lakh", "budget_max_lakh"):
        try:
            out[k] = None if out[k] is None else float(out[k])
        except (TypeError, ValueError):
            out[k] = None
    for k in ("wants_execution", "just_exploring", "asked_price", "existing_client_complaint", "wants_human"):
        v = out[k]
        if isinstance(v, str):
            v = v.strip().lower() in ("true", "yes", "1")
        out[k] = v if v is None else bool(v)
    return out


def _has(text, words):
    t = (text or "").lower() + " "
    return any(w in t for w in words)


def location_status(loc):
    if not loc:
        return "unknown"
    t = " " + loc.lower() + " "
    if any(w in t for w in AREAS_OUT):
        return "out"
    if any(w in t for w in AREAS_IN):
        return "in"
    return "unknown"


# --------------------------------------------------------------------------------------
# The rubric in code (qualified.md) - returns a decision and everything the speaker needs
# --------------------------------------------------------------------------------------
def evaluate(facts, now=None, skip=()):
    f = clean_facts(facts)
    crit = {}
    flags = []

    # 1. Real project - not just advice (and inside what the studio does: services.md)
    c1, r1 = "pass", "Wants design + execution"
    pt = f["project_type"]
    if f["wants_execution"] is False or pt == "advice_only":
        c1, r1 = "fail", "Wants ideas/advice only - minimum engagement is a room redesign with execution"
    elif pt == "out_of_scope":
        c1, r1 = "fail", "Restaurant/hotel/retail/gym - outside what Aangan does"
    elif pt == "office" and f["area_sqft"] and f["area_sqft"] > COMMERCIAL_MAX_SQFT:
        c1, r1 = "fail", "Office larger than ~%d sq ft" % COMMERCIAL_MAX_SQFT
    elif pt == "office" and f["area_sqft"] and f["area_sqft"] < COMMERCIAL_MIN_SQFT:
        c1, r1 = "fail", "Commercial space under ~%d sq ft (front-desk practice, not in services.md)" % COMMERCIAL_MIN_SQFT
    elif f["just_exploring"]:
        c1, r1 = "fail", "Early stage / just exploring - no commitment to a project yet"
    elif pt is None:
        c1, r1 = "unclear", "Project type not known yet"
    elif (pt == "other") or (pt == "single_room" and f["wants_execution"] is None):
        c1, r1 = "unclear", "Need to confirm they want a full redesign with execution"
    crit[1] = {"status": c1, "reason": r1}

    # 2. Service area (Pune + PCMC)
    ls = location_status(f["location_text"])
    if ls == "in":
        crit[2] = {"status": "pass", "reason": "In service area (%s)" % f["location_text"]}
    elif ls == "out":
        crit[2] = {"status": "fail", "reason": "Outside Pune/PCMC (%s) - no vendor network there" % f["location_text"]}
    else:
        crit[2] = {"status": "unclear", "reason": "Location not confirmed"}

    # 3. Realistic timeline (services.md: < 6 weeks to be ready is impossible)
    ts, wk = f["timeline_status"], f["ready_by_weeks"]
    if ts == "hard_deadline" and wk is not None:
        if wk < MIN_LEAD_WEEKS:
            crit[3] = {"status": "fail", "reason": "Needs it ready in ~%g weeks; design alone takes 3-4 weeks and execution 8+" % wk}
        else:
            crit[3] = {"status": "pass", "reason": "Needs it in ~%g weeks" % wk}
            if wk < TIGHT_WEEKS:
                flags.append("Tight timeline (~%g weeks) - designer to confirm feasibility" % wk)
    elif ts in ("flexible", "start_only"):
        crit[3] = {"status": "pass", "reason": "No hard deadline" if ts == "flexible" else "Wants to start soon; no hard completion date"}
        if ts == "start_only":
            flags.append("Wants to start now - confirm completion expectation at consultation")
    else:
        crit[3] = {"status": "unclear", "reason": "Timeline not known yet"}

    # 4. Budget band (broadly) - never probe, never quote. Only a volunteered, clearly-too-low number fails.
    bmax = f["budget_max_lakh"] if f["budget_max_lakh"] is not None else f["budget_min_lakh"]
    if bmax is None:
        crit[4] = {"status": "pass", "reason": "Budget not mentioned - treated as qualified"}
        flags.append("Budget not volunteered (do not probe) - designer establishes fit")
    else:
        floor = ROOM_FLOOR_LAKH
        area = f["area_sqft"]
        if area and pt in ("full_home", "office"):  # per-sq-ft floor only makes sense for whole-space scopes
            rate = 1200 if pt == "office" else 1800
            floor = max(floor, 0.5 * area * rate / 100000.0)  # < 50% of lowest indicative rate = clearly misaligned
        if bmax < floor:
            crit[4] = {"status": "fail", "reason": "Volunteered budget (up to %g lakh) is clearly below any project of this scope" % bmax}
        else:
            crit[4] = {"status": "pass", "reason": "Volunteered budget is within a plausible band"}

    # 5. Decision-maker (never pushed; unclear = qualified + note)
    dm = f["decision_maker"]
    if dm in ("self", "authorised"):
        crit[5] = {"status": "pass", "reason": "Decision-maker on the call" if dm == "self" else "Authorised by the decision-maker"}
    elif dm == "researching_for_others":
        crit[5] = {"status": "unclear", "reason": "Caller is checking on behalf of others"}
        flags.append("Caller is researching for family - decision-makers (owners) should attend the consultation")
    else:
        crit[5] = {"status": "unclear", "reason": "Not confirmed"}
        flags.append("Decision-maker not confirmed on the call")

    fails = [k for k in (1, 2, 3, 4) if crit[k]["status"] == "fail"]
    out = {"criteria": crit, "flags": flags, "fails": fails}

    # Decision ladder
    if f["existing_client_complaint"] or f["wants_human"]:
        out.update(decision="escalate", reason="Existing-client complaint or caller insists on a senior person")
    elif fails:
        reasons = {1: "not_a_real_project", 2: "outside_service_area", 3: "timeline_not_possible", 4: "budget_misaligned"}
        key = reasons[fails[0]]
        if f["just_exploring"] and fails == [1]:
            key = "exploring_only"
        out.update(decision="decline", reason=key, multiple=len(fails) >= 2)
        out["nurture"] = key in ("exploring_only", "timeline_not_possible")
    else:
        # ask one question at a time: scope -> location -> timeline, then collect the rest of the handoff
        order = [(1, "project"), (2, "location"), (3, "timeline")]
        for k, fld in order:
            if crit[k]["status"] == "unclear" and fld in skip:
                flags.append("Not confirmed on the call: %s" % fld)
        pending = next((fld for k, fld in order if crit[k]["status"] == "unclear" and fld not in skip), None)
        out["qual"] = "ask" if pending else "forward"
        if pending:
            out.update(decision="ask", ask=pending)
        else:
            more = next_handoff_field(f, skip)
            if more:
                out.update(decision="ask", ask=more)
            else:
                out.update(decision="forward", reason="Passes all five criteria")
    out.setdefault("qual", out["decision"])
    out["priority"] = priority(f, crit) if out["decision"] in ("forward", "ask") else None
    return out


def next_handoff_field(f, skip=()):
    """Everything the designer would otherwise have to re-ask. Each is asked at most once by the speaker."""
    for key, fld in (("area_sqft", "size"), ("property_state", "property_state"), ("caller_name", "name"), ("preferred_slot", "slot")):
        if not f[key] and fld not in skip:
            return fld
    return None


def priority(f, crit):
    score = 0
    if f["decision_maker"] in ("self", "authorised"):
        score += 2
    if f["timeline_status"] in ("start_only",) or (f["ready_by_weeks"] and f["ready_by_weeks"] <= 20):
        score += 2
    if f["referral_source"]:
        score += 1
    if f["area_sqft"] and f["area_sqft"] >= 1000 or f["project_type"] in ("office",):
        score += 1
    if f["budget_max_lakh"]:
        score += 1
    if f["just_exploring"] or f["decision_maker"] == "researching_for_others":
        score -= 2
    return "HOT" if score >= 4 else "WARM"


# --------------------------------------------------------------------------------------
# Pricing guardrail (pricing.md: no number, range or per-sq-ft figure may ever be said)
# --------------------------------------------------------------------------------------
_PRICE_PAT = re.compile(
    r"(₹|\brs\.?\s*\d|\binr\b|\blakhs?\b|\blacs?\b|\bcrores?\b|\bper\s*(sq|square)|/\s*(sq|square)|"
    r"\d\s*(k|l)\b|\bstarts?\s+(at|from)\b|\bapproximately\s+\d+\s*(per|/)|\b\d[\d,\.]*\s*(per|a)\s*(sq|square))",
    re.I,
)


def guard_reply(text):
    """If the speaker ever leaks a money figure, replace the whole reply with the approved line."""
    if not text or _PRICE_PAT.search(text):
        return APPROVED_PRICING_LINE, True
    return text, False


def asks_for_price(text):
    return bool(re.search(r"(how much|cost|price|pricing|rate|per sq|charge|ballpark|rough(ly)? (idea|range)|quote|estimate)", text or "", re.I))


# --------------------------------------------------------------------------------------
# Regex fallback extractor: works with NO API key (demo mode) and powers the offline back-test
# --------------------------------------------------------------------------------------
_LOCALITIES = sorted(set(AREAS_IN + AREAS_OUT), key=len, reverse=True)


def heuristic_extract(caller_lines, now=None, prev=None):
    now = now or datetime.now(IST)
    f = clean_facts(prev)
    text = " \n".join(caller_lines)
    t = text.lower()

    m = re.search(r"(?i:my name is|this is|i'?m|i am|myself|name'?s)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
    if m and m.group(1).lower() not in ("calling", "looking", "in", "a", "not", "just", "the", "from", "planning", "getting", "doing"):
        f["caller_name"] = m.group(1)

    # location
    for loc in _LOCALITIES:
        if re.search(r"\b" + re.escape(loc.strip()) + r"\b", t):
            f["location_text"] = loc.strip().title()
            break

    # size
    m = re.search(r"(\d[\d,]*)\s*(?:sq\.?\s*ft|sqft|square\s*feet|sq\s*feet)", t)
    if m:
        f["area_sqft"] = float(m.group(1).replace(",", ""))

    # project type
    if _has(t, OUT_OF_SCOPE_WORDS):
        f["project_type"] = "out_of_scope"
    elif _has(t, ["office", "startup", "clinic", "workstation", "coworking", "co-working"]):
        f["project_type"] = "office"
    elif _has(t, ["ideas", "suggestions", "advise", "advice", "consultation only", "colours", "colors"]) and not _has(t, ["full redesign", "complete redesign", "execution"]):
        f["project_type"] = "advice_only"
        f["wants_execution"] = False
    elif _has(t, ["whole thing", "full home", "full redesign", "complete redesign", "full interiors", "poora ghar", "entire", "end-to-end", "end to end", "full package", "complete"]) or re.search(r"\b[34]\s*bhk\b", t) and _has(t, ["redo", "design", "interior"]):
        f["project_type"] = "full_home"
    elif _has(t, ["living room", "bedroom", "kitchen", "room"]):
        n = sum(1 for w in ["living room", "bedroom", "kitchen", "dining"] if w in t)
        f["project_type"] = "partial_home" if n >= 2 else "single_room"
    elif _has(t, ["flat", "apartment", "home", "villa", "house", "bhk"]):
        f["project_type"] = f["project_type"] or "full_home"
    m = re.search(r"((?:kitchen|bedroom|living|wardrobe|dining|study)[^.]{0,80})", t)
    if m:
        f["scope_text"] = m.group(1)[:120]
    if _has(t, ["execution", "full redesign", "complete redesign", "design and execution"]):
        f["wants_execution"] = True if f["wants_execution"] is None else f["wants_execution"]
    if _has(t, ["just exploring", "just looking", "early stage", "exploring for now", "maybe later", "still exploring"]):
        f["just_exploring"] = True

    # property state
    for key, label in [("bare", "bare / empty"), ("possession", "new possession"), ("builder flat", "builder flat"),
                       ("new construction", "new construction"), ("moved in", "lived in"), ("rented", "rented"), ("lived here", "lived in")]:
        if key in t:
            f["property_state"] = label
            break

    # budget (lakh)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)\s*(?:lakh|lac)", t) or None
    if m:
        f["budget_min_lakh"], f["budget_max_lakh"] = float(m.group(1)), float(m.group(2))
    else:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)", t)
        if m:
            f["budget_max_lakh"] = float(m.group(1))

    # timeline
    if _has(t, ["no rush", "flexible", "whenever", "no specific", "plenty of time", "in no rush", "not in a rush"]):
        f["timeline_status"] = "flexible"
        f["timeline_text"] = "flexible / no rush"
    m = re.search(r"in\s+(?:about\s+|around\s+|another\s+)?(\d+|one|two|three|four|five|six)\s+weeks?", t) or re.search(r"(\d+|three|two|four)\s+weeks?\s+(?:max|maximum|away)", t)
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
    if m and f["timeline_status"] != "flexible":
        n = m.group(1)
        wk = float(words.get(n, n))
        if "possession" in t and "six weeks" in t or re.search(r"possession[^.]{0,40}weeks", t):
            f["timeline_status"] = "start_only"
            f["timeline_text"] = "possession in ~%g weeks, wants to start design now" % wk
        else:
            f["timeline_status"] = "hard_deadline"
            f["ready_by_weeks"] = wk
            f["timeline_text"] = "needs it in ~%g weeks" % wk
    if "after diwali" in t:
        f["timeline_status"] = "start_only"
        f["timeline_text"] = "wants to start after Diwali"
        f["ready_by_weeks"] = None
    elif _has(t, ["diwali"]) and f["timeline_status"] is None:
        f["timeline_status"] = "hard_deadline"
        f["ready_by_weeks"] = 3.0
        f["timeline_text"] = "before Diwali"
    months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
    for i, mn in enumerate(months):
        if re.search(mn + r"\s+start|start[^.]{0,25}" + mn, t) and f["timeline_status"] is None:
            f["timeline_status"] = "start_only"
            f["timeline_text"] = "start in %s" % mn.title()
            break
        if re.search(r"\b(by|till|until|move in|move-in|complete by|done by)\s+" + mn, t) or re.search(r"\b(move[sd]?|moving)\s+in\s+" + mn, t) or re.search(r"\bin\s+" + mn, t) or re.search(mn + r"\s+(if possible|next year)|operational[^.]{0,30}" + mn, t):
            year = now.year + (1 if i + 1 <= now.month else 0)
            target = datetime(year, i + 1, 28, tzinfo=IST)
            wk = max(0.0, (target - now).days / 7.0)
            if f["timeline_status"] not in ("flexible", "hard_deadline"):
                f["timeline_status"] = "hard_deadline"
                f["ready_by_weeks"] = round(wk, 1)
                f["timeline_text"] = "by %s" % mn.title()
            break
    if f["timeline_status"] is None and _has(t, ["right away", "immediately", "asap", "as soon as", "start now", "start the design", "can start"]):
        f["timeline_status"] = "start_only"
        f["timeline_text"] = "wants to start now"

    # decision maker
    if _has(t, ["i'm the owner", "i am the owner", "are you the owner", "yes — myself", "my husband and i", "my wife and i", "founder", "we both", "myself and my", "decision", "he knows we're calling", "happy to go ahead", "said to go ahead", "both want"]) or re.search(r"\bwe own\b|\bmy (flat|home|house)\b|\bour (flat|home)\b", t):
        f["decision_maker"] = "self"
    if _has(t, ["for my parents", "for my in-laws", "initial checking", "initial research", "doing the initial", "call on behalf"]):
        f["decision_maker"] = "researching_for_others"

    # misc intents
    if asks_for_price(t):
        f["asked_price"] = True
    if _has(t, ["hasn't replied", "not acceptable", "complain", "my designer", "project has been going", "speak to someone right now", "unacceptable"]):
        f["existing_client_complaint"] = True
    if _has(t, ["speak to a human", "speak to someone", "talk to a person", "senior person", "speak to nikhil", "manager"]):
        f["wants_human"] = True
    for key in ["friend", "referred", "asked me to call", "got your number", "instagram", "linkedin", "google", "builder", "recommend"]:
        if key in t:
            f["referral_source"] = key
            break
    m = re.search(r"(weekends?(?: only)?|weekdays? after \d+ ?(?:pm)?|any weekday[a-z ]*|saturday[^.]{0,20}|sunday[^.]{0,20}|this week|next week|after 6|mornings?|evenings?|afternoons?)", t)
    if m:
        f["preferred_slot"] = m.group(1)
    return f


# --------------------------------------------------------------------------------------
# LLM access (Anthropic Haiku 5.5 by default, Gemini as alternative, none = demo mode)
# --------------------------------------------------------------------------------------
def provider():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return "none"


def model_name():
    p = provider()
    return {"anthropic": ANTHROPIC_MODEL, "gemini": LAST_MODEL.get("name") or GEMINI_MODEL}.get(p, "demo-rules")


def _post_json(url, payload, headers, timeout=25):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=dict(headers, **{"content-type": "application/json"}), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError("LLM HTTP %s: %s" % (e.code, e.read().decode()[:300]))


def llm(system, user, max_tokens=700):
    """Returns (text, usage) with usage = {input, output}. Raises on failure."""
    p = provider()
    if p == "anthropic":
        body = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "thinking": {"type": "disabled"},
            "output_config": {"effort": "low"},
        }
        r = _post_json("https://api.anthropic.com/v1/messages", body,
                       {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
        txt = "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
        u = r.get("usage", {})
        return txt, {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0)}
    if p == "gemini":
        last = None
        for m in GEMINI_MODELS:  # try the next model if one is retired or overloaded
            body = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
            }
            if "lite" not in m:
                body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "minimal"}
            try:
                r = _post_json("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s" % (m, os.environ["GEMINI_API_KEY"]), body, {})
                parts = r["candidates"][0]["content"]["parts"]
                txt = "".join(x.get("text", "") for x in parts if not x.get("thought"))
                u = r.get("usageMetadata", {})
                LAST_MODEL["name"] = m
                return txt, {"input": u.get("promptTokenCount", 0), "output": u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)}
            except Exception as e:
                last = e
        raise last
    raise RuntimeError("no LLM key configured")


def cost_inr(usage, prov=None):
    prov = prov or provider()
    if prov not in PRICES:
        return 0.0
    pin, pout = PRICES[prov]
    usd = usage.get("input", 0) / 1e6 * pin + usage.get("output", 0) / 1e6 * pout
    return round(usd * USD_INR, 4)


def _parse_json(txt):
    txt = txt.strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e + 1])


EXTRACT_SYSTEM = """You read a phone-call transcript between an AI receptionist and a caller to Aangan Studio, an interior design studio in Pune. Extract facts the CALLER has stated. Use the caller's LATEST position if they changed their mind. Never guess: use null when not stated. Output ONLY a JSON object with exactly these keys:
caller_name, project_type (full_home | partial_home | single_room | office | advice_only | out_of_scope | other), scope_text, wants_execution (true if they want design + execution; false if they only want ideas/advice/colour suggestions; null if unknown), just_exploring (true if "just exploring / early stage / maybe later"), location_text (locality/city of the SITE), area_sqft (number, carpet area), property_state (e.g. bare builder flat, new possession, lived-in, rented), timeline_status (hard_deadline ONLY if they say the finished project is needed by a date/event, e.g. 'done by March', 'before Diwali', 'guests in 3 weeks'. A possession/handover/keys date is NOT a deadline, it is when they can start, so use start_only; flexible if no rush; start_only if they only say they want to start now/soon with no completion date; unknown), ready_by_weeks (number of weeks from TODAY until they need the project finished, only for hard_deadline), timeline_text, budget_min_lakh, budget_max_lakh (only if the caller volunteered a figure; in lakh), decision_maker (self = caller decides or is the owner with the spouse's go-ahead; authorised = calling for someone who authorised them; researching_for_others = only doing initial research for family/others who will decide; unknown), referral_source, preferred_slot (days/times they prefer for a consultation), asked_price (true if they asked about cost/price/rate/ballpark at any point), existing_client_complaint (true if they are an existing client complaining about a project/designer), wants_human (true if they ask for a person/senior/manager), language, notes (one short line of anything useful the designer should know).
Homes (flats, villas, rooms) are full_home / partial_home / single_room. Offices, clinics, studios, coworking and any other work-space fit-out are project_type office, which Aangan DOES do: NEVER label them out_of_scope. out_of_scope is ONLY for restaurants, hotels, cafes, retail stores/showrooms, gyms and salons. If unsure, use other, never out_of_scope or advice_only. Today is %s (IST)."""

SPEAK_SYSTEM = """You are the voice of Aangan Studio's AI phone assistant (Aangan Studio does interior design + execution for homes and small offices in Pune and PCMC). You are speaking aloud on a phone call, so: warm, plain, brief (1-3 short sentences, under 45 words), one question at a time, no lists, no emojis, no markdown. If the caller writes in Hinglish or Marathi, answer in the same language/script style. You are an AI and say so honestly if asked.
HARD RULES - never break these:
- NEVER state any price, range, rate, per-square-foot figure, budget figure or estimate, not even 'roughly' or 'starting from'. If they ask about cost, say pricing depends on the site, materials and scope and the designer will walk them through it at the free consultation.
- NEVER promise a specific designer, date or time; the team confirms slots.
- Do not give design advice or opinions on materials.
- Follow the DIRECTIVE exactly; do not ask anything the directive doesn't ask for."""


_ADVICE = re.compile(r"(ideas|suggest|advice|advise|advisory|consult(?:ation)? only|colou?rs?\b|styling|arrange|rearrange|just (?:want|looking)|diy|myself)", re.I)
_EXPLORE = re.compile(r"(explor|just looking|browsing|early stage|maybe later|not (?:sure|ready)|thinking about|window shopping|research|portfolio|brochure)", re.I)
_COMPLAIN = re.compile(r"(complain|not acceptable|unacceptable|hasn'?t replied|no reply|not replied|my designer|my project|escalat|senior|manager|nikhil|speak to (?:a |some)|talk to (?:a |some)|human|person)", re.I)
_DEADLINE = re.compile(r"(\bby\b|before|within|done|ready|complete|finish|move[- ]?in|moving in|operational|deadline|guests|arriv|diwali|wedding|festival|max(?:imum)?\b|urgent|latest|open(?:ing)?\b|in \d+ weeks?|in (?:one|two|three|four|five) weeks?)", re.I)
_OFFICE = re.compile(r"(office|startup|clinic|workstation|cowork|co-work|cabin|studio)", re.I)


def sanity_check(f, caller_text):
    """The AI may keep a lead alive, but it may not CLOSE one unless the caller's own words back it up."""
    notes = []
    if f["project_type"] == "out_of_scope" and not _has(caller_text, OUT_OF_SCOPE_WORDS):
        f["project_type"] = "office" if _OFFICE.search(caller_text) else "other"
        notes.append("project type reset")
    if (f["wants_execution"] is False or f["project_type"] == "advice_only") and not _ADVICE.search(caller_text):
        f["wants_execution"] = None
        if f["project_type"] == "advice_only":
            f["project_type"] = "other"
        notes.append("advice-only claim not supported by caller words")
    if f["just_exploring"] and not _EXPLORE.search(caller_text):
        f["just_exploring"] = False
        notes.append("exploring claim not supported")
    if (f["existing_client_complaint"] or f["wants_human"]) and not _COMPLAIN.search(caller_text):
        f["existing_client_complaint"] = f["wants_human"] = False
        notes.append("escalation claim not supported")
    if f["timeline_status"] == "hard_deadline" and not _DEADLINE.search(caller_text):
        f["timeline_status"], f["ready_by_weeks"] = "start_only", None   # a possession/handover date is a start, not a deadline
        notes.append("deadline not supported by caller words")
    if (f["budget_min_lakh"] or f["budget_max_lakh"]) and not re.search(r"\d|lakh|lac|crore", caller_text, re.I):
        f["budget_min_lakh"] = f["budget_max_lakh"] = None
        notes.append("budget not stated by caller")
    if notes:
        f["notes"] = ((f.get("notes") or "") + " [safety net: " + "; ".join(notes) + "]").strip()
    return f


def extract_facts(transcript, prev_facts, now=None):
    """transcript = [{'role':'agent'|'caller','text':...}]. Returns (facts, usage)."""
    now = now or datetime.now(IST)
    caller_lines = [m["text"] for m in transcript if m["role"] == "caller"]
    if provider() == "none":
        return heuristic_extract(caller_lines, now, prev_facts), {"input": 0, "output": 0}
    convo = "\n".join(("Caller: " if m["role"] == "caller" else "Assistant: ") + m["text"] for m in transcript)
    try:
        txt, usage = llm(EXTRACT_SYSTEM % now.strftime("%A %d %B %Y"), convo, 600)
        f = sanity_check(clean_facts(_parse_json(txt)), " ".join(caller_lines))
        # keep sticky facts the model may have dropped, and never let the LLM hide a price ask
        base = heuristic_extract(caller_lines, now, None)
        if base.get("asked_price"):
            f["asked_price"] = True
        return f, usage
    except Exception as e:  # never break a live call: fall back to rules
        LAST_ERROR["msg"] = str(e)[:200]
        f = heuristic_extract(caller_lines, now, prev_facts)
        f["notes"] = ((f.get("notes") or "") + " [fallback extractor: %s]" % str(e)[:80]).strip()
        return f, {"input": 0, "output": 0}


GREETING = ("Namaste, thank you for calling Aangan Studio. I'm Aangan's AI assistant, and this call is recorded so the design team "
            "doesn't have to ask you everything again. How can I help you today?")

DECLINE_LINES = {
    "outside_service_area": "Thank you for calling. We only work in Pune and PCMC right now, because our contractors and vendors are on site there, so I wouldn't be able to serve you well in {loc}. I'm sorry we can't help, and thank you for thinking of us.",
    "not_a_real_project": "Thank you for being clear about that. We're a design-and-execution studio, so we take on full redesigns rather than advice or styling visits. If you decide to go ahead with a full project later, please call us back.",
    "exploring_only": "That's completely fine, there's no hurry. Whenever you're ready to take a project forward, just call or message us and we'll set up a free consultation.",
    "timeline_not_possible": "I want to be honest with you: our design phase alone takes three to four weeks, and execution follows, so we couldn't do justice to a project needed that soon. If your date can move, I'd be happy to note your details for a later start.",
    "budget_misaligned": "I appreciate you sharing that. For a project of that scope with full execution, that would be well below what we could deliver, and I wouldn't want to waste your time with a consultation. A local contractor at that price point may serve you better.",
    "multiple": "This sounds like it may not be the right fit for us right now, but please feel free to reach out if your timeline or scope changes. Thank you for calling.",
}

ASK_LINES = {
    "project": "Could you tell me a little about what you'd like to do, which spaces, and whether it's a home or an office?",
    "location": "Which area of Pune or Pimpri-Chinchwad is the property in?",
    "timeline": "When would you need the project complete, roughly?",
    "size": "Roughly how big is the space, in carpet area square feet?",
    "property_state": "Is the space empty or newly handed over, or are you living in it now?",
    "name": "May I have your name, please?",
    "slot": "Which days and times suit you best for a free consultation, with a designer visiting the site?",
}

ESCALATE_LINE = ("I'm very sorry about this. I'm passing it to our studio head right now so a senior person calls you back, "
                 "usually within fifteen minutes. Could I confirm your name and your designer's name?")


def make_directive(decision, facts):
    f = clean_facts(facts)
    price = ""
    if decision.get("deflect_price"):
        price = " The caller asked about price: first say, in your own words, exactly this idea and nothing more specific: '%s' (without repeating the booking offer if you are about to ask a question)." % APPROVED_PRICING_LINE
    d = decision["decision"]
    if d == "ask":
        return "ASK: %s%s" % (ASK_LINES[decision["ask"]], price)
    if d == "decline":
        return "DECLINE gracefully and kindly, no pricing, no blame: %s" % template_reply(decision, f)
    if d == "escalate":
        return "ESCALATE: %s" % ESCALATE_LINE
    if d == "forward":
        return ("CLOSE: thank them by name if known, say everything they've told you has been passed to the design team so they won't "
                "need to repeat it, and that someone will confirm the consultation shortly. Ask if there's anything else.%s" % price)
    return "ASK: how can I help?"


def template_reply(decision, facts):
    f = clean_facts(facts)
    d = decision["decision"]
    reply = ""
    if d == "decline":
        if decision.get("multiple"):
            reply = DECLINE_LINES["multiple"]
        else:
            reply = DECLINE_LINES[decision["reason"]].replace("{loc}", f["location_text"] or "your area")
    elif d == "escalate":
        reply = ESCALATE_LINE
    elif d == "forward":
        nm = (", " + f["caller_name"].split()[0]) if f["caller_name"] else ""
        reply = ("Thank you%s. I've passed everything you told me to our design team, so you won't need to repeat it. "
                 "Someone will call you shortly to confirm your consultation. Is there anything else I can help with?" % nm)
    elif d == "ask":
        reply = ASK_LINES[decision["ask"]]
    if decision.get("deflect_price") and d in ("ask", "forward"):
        reply = APPROVED_PRICING_LINE.replace(" I can book that for you right now if you'd like.", "") + " " + reply
    return reply


def speak(transcript, decision, facts):
    """Returns (reply, usage, price_blocked)."""
    directive = make_directive(decision, facts)
    if provider() == "none":
        r, blocked = guard_reply(template_reply(decision, facts))
        return r, {"input": 0, "output": 0}, blocked
    convo = "\n".join(("Caller: " if m["role"] == "caller" else "You: ") + m["text"] for m in transcript[-12:])
    try:
        txt, usage = llm(SPEAK_SYSTEM, "CALL SO FAR:\n%s\n\nDIRECTIVE: %s\n\nWrite only what you say next." % (convo, directive), 220)
        reply, blocked = guard_reply(txt.strip().strip('"'))
        return reply, usage, blocked
    except Exception as e:
        LAST_ERROR["msg"] = str(e)[:200]
        r, blocked = guard_reply(template_reply(decision, facts))
        return r, {"input": 0, "output": 0}, blocked


# --------------------------------------------------------------------------------------
# Handoff note (what the designer receives on Telegram) + lead record
# --------------------------------------------------------------------------------------
def human_budget(f):
    lo, hi = f.get("budget_min_lakh"), f.get("budget_max_lakh")
    if lo and hi and lo != hi:
        return "%g-%g lakh (volunteered)" % (lo, hi)
    if hi or lo:
        return "up to %g lakh (volunteered)" % (hi or lo)
    return "not mentioned (not probed)"


def after_hours(ts):
    h = ts.astimezone(IST)
    return not (OFFICE_OPEN <= h.hour < OFFICE_CLOSE) or h.weekday() == 6


def build_note(facts, decision, phone, started_at, transcript_len):
    f = clean_facts(facts)
    c = decision.get("criteria", {})
    ts = started_at.astimezone(IST)
    ah = after_hours(ts)
    callback = "next morning 10:00" if ah else "within 30 minutes"
    lines = [
        "%s LEAD  |  %s" % (decision.get("priority") or "WARM", ts.strftime("%a %d %b, %I:%M %p")),
        "",
        "%s  |  %s" % (f["caller_name"] or "Name not given", phone or "number from caller ID"),
        "%s, %s" % ((f["project_type"] or "project").replace("_", " ").title(), f["location_text"] or "location ?"),
        "Size: %s  |  Site: %s" % ("%g sq ft carpet" % f["area_sqft"] if f["area_sqft"] else "not given", f["property_state"] or "not given"),
        "Scope: %s" % (f["scope_text"] or "as discussed"),
        "Timeline: %s" % (f["timeline_text"] or f["timeline_status"] or "not given"),
        "Budget: %s" % human_budget(f),
        "Decision-maker: %s" % ((f["decision_maker"] or "unknown").replace("_", " ")),
        "Came via: %s" % (f["referral_source"] or "not stated"),
        "Preferred consultation: %s" % (f["preferred_slot"] or "not given - please offer slots"),
        "",
        "Already collected on the call (don't ask again): " + ", ".join(
            lab for lab, key in (("project", "project_type"), ("location", "location_text"), ("size", "area_sqft"), ("site state", "property_state"),
                                 ("timeline", "timeline_text"), ("name", "caller_name"), ("preferred slot", "preferred_slot")) if f[key]) + ".",
    ]
    if f["asked_price"]:
        lines.append("Asked about price: told pricing is confirmed by the designer at consultation. No figure was given.")
    if decision.get("flags"):
        lines.append("")
        lines.append("Watch-outs:")
        lines += ["  - " + x for x in decision["flags"]]
    if f["notes"]:
        lines.append("Note: %s" % f["notes"])
    lines += ["", "Call back %s%s." % (callback, " (call came after hours)" if ah else ""),
              "Criteria: " + "  ".join("%d:%s" % (k, c[k]["status"].upper()) for k in sorted(c))]
    return "\n".join(lines)


def build_decline_note(facts, decision, phone, started_at):
    f = clean_facts(facts)
    ts = started_at.astimezone(IST)
    return "CLOSED - %s  |  %s  |  %s  |  %s" % (decision.get("reason", "").replace("_", " "), ts.strftime("%d %b %I:%M %p"), f["caller_name"] or "no name", phone or "caller ID")


def build_escalation_note(facts, phone, started_at, transcript):
    f = clean_facts(facts)
    ts = started_at.astimezone(IST)
    last = [m["text"] for m in transcript if m["role"] == "caller"][-3:]
    return ("URGENT - EXISTING CLIENT ESCALATION  |  %s\n\n%s  |  %s\nCaller asked for a senior callback (promised within ~15 min).\n"
            "What they said: %s") % (ts.strftime("%a %d %b, %I:%M %p"), f["caller_name"] or "name?", phone or "caller ID", " / ".join(last))


# --------------------------------------------------------------------------------------
# Telegram (handoff channel) - sends only if the env vars are set
# --------------------------------------------------------------------------------------
def telegram_chat_id():
    """TELEGRAM_CHAT_ID from the environment, else the chat registered with /register."""
    if os.environ.get("TELEGRAM_CHAT_ID"):
        return os.environ["TELEGRAM_CHAT_ID"]
    try:
        import _store
        return _store.get_setting("telegram_chat")
    except Exception:
        return None


def telegram_configured():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and telegram_chat_id())


def send_telegram(text, lead_id, urgent=False):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), telegram_chat_id()
    if not (tok and chat):
        return {"sent": False, "reason": "Telegram not configured"}
    body = {"chat_id": chat, "text": ("\U0001f6a8 " if urgent else "") + text}
    if not urgent:
        body["reply_markup"] = {"inline_keyboard": [[{"text": "✅ I'll take it", "callback_data": "claim:%s" % lead_id}]]}
    try:
        r = _post_json("https://api.telegram.org/bot%s/sendMessage" % tok, body, {}, 10)
        return {"sent": bool(r.get("ok")), "message_id": r.get("result", {}).get("message_id")}
    except Exception as e:
        return {"sent": False, "reason": str(e)[:150]}
