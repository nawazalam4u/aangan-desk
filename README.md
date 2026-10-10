# Aangan Desk

An AI phone assistant for Aangan Studio (MESA Case 03). It answers every incoming enquiry call instantly, qualifies the caller with Nikhil's five-criteria rubric, never quotes a price, and sends the designer a complete handoff note on Telegram. A dashboard shows volume, response time, cost and the pipeline it creates.

**Pages:** `/` live call simulator (English, Hindi, Marathi) · `/dashboard` Nikhil's dashboard (charts, funnel, alerts, filters) · `/connect` how one call travels through every system, with live status lights, test buttons and the HubSpot explainer · `/brief` automation brief, Nine Checks, the Cut, components map, red flags.

**Deploys:** this repo is linked to Vercel, so every push to `main` redeploys https://aangan-desk.vercel.app. The database is Neon Postgres (connected through the `DATABASE_URL` setting on Vercel).

## How it works

```
caller -> voice layer (demo: browser mic) -> /api/turn -> facts (AI) -> rules (code) -> reply (AI) -> price filter (code)
call ends -> /api/finalize -> handoff note -> Telegram (+ database) -> /dashboard
```

The AI only extracts facts and words the reply. **Code decides** (`api/_core.py`): the five criteria from `data/qualified.md`, service area and timeline rules from `data/services.md`, and a filter that stops any price leaving the system (`data/pricing.md`).

> The course case files (`services.md`, `pricing.md`, `qualified.md` and the 40 transcripts) are not included in this public repo. The rules in `api/_core.py` were written from them; the back-test and scenario tests need `tests/enquiries.py` and `data/`, which stay private.

## Test it without any keys

```bash
python3 dev_server.py          # http://localhost:3000  (demo mode: rules-based voice)
python3 -I tests/backtest.py   # the 40 real September enquiries through the rules
python3 -I tests/scenarios.py  # the 9 demo calls end to end + the price-guardrail attack
python3 -I tests/voice_sim.py  # simulated phone calls through /api/voice
python3 -I tests/hubspot_mock.py  # HubSpot requests against a fake HubSpot
python3 -I tests/vaani_sim.py    # Vaani webhooks: qualified, closed, escalated, price-leak alert
```

## Turn things on (Vercel > Settings > Environment Variables)

| Variable | What it switches on |
|---|---|
| `GEMINI_API_KEY` | The real AI (Gemini 3.1 Flash-Lite, with 3.5 Flash as backup). Or `ANTHROPIC_API_KEY` for Claude Haiku 5.5. Check `/api/health?probe=1`. |
| `TELEGRAM_BOT_TOKEN` | Handoff notes to the designers' private group, with an "I'll take it" button. Send `/register <dashboard key>` in the group to choose where notes go. |
| `TELEGRAM_WEBHOOK_SECRET` | Makes the button work (point the bot webhook to `/api/telegram` with the same secret) |
| `DATABASE_URL`, `DASHBOARD_KEY` | Shared Neon Postgres database (the table is created automatically) so the dashboard shows every call, locked by a key |
| `HUBSPOT_TOKEN` | CRM sync (the HubSpot integration): each qualified / call-back / escalated lead becomes a HubSpot contact + timeline note + a call-back task, and a deal for qualified leads). Set `HUBSPOT_PORTAL_ID` to make dashboard rows link straight to the HubSpot contact. HubSpot **service key** (Settings > Development > Keys > Service Keys) with scopes `crm.objects.contacts.read/write` and `crm.objects.deals.read/write`; notes and tasks need no extra scope. Optional `HUBSPOT_DEAL_STAGE` (default `appointmentscheduled`). |

Without a database the dashboard shows calls made in the same browser. With the database set but no `DASHBOARD_KEY`, the dashboard stays locked on purpose, because it holds callers' phone numbers.

## The real voice agent (Vaani)

The phone voice is a **Vaani** agent (`aangan-receptionist`, app.vaanivoice.ai). Vaani owns the phone number, speech recognition and the voice; its instructions are in `vaani/receptionist_prompt.txt` (Nikhil's rules + the no-price rule).

- **After every call** Vaani posts the transcript to `/api/vaani?key=<VAANI_WEBHOOK_SECRET>` (Vaani > Developers > Webhooks, events *Call Started* + *Call Post-Processing*). Our code re-applies the five rules, audits the agent's words for any price (Telegram alert if one slips), and sends the lead to Telegram, Neon, HubSpot and the dashboard.
- **Calling customers back:** the dashboard's "Call back with AI" button calls `/api/callback`, which asks Vaani (`VAANI_API_KEY`, `VAANI_AGENT_ID`) to ring the customer.
- **Phone number:** buy one in Vaani > Telephony (Indian numbers via Vobiz, about Rs 100 setup + Rs 500-999/month) and select it under the agent's Deploy > Inbound Phone Number.
- Tested with `python3 -I tests/vaani_sim.py` and with a real agent conversation replayed to the live webhook.

## Real phone calls without Vaani (Twilio-style)

`/api/voice` is a webhook a phone provider calls for every call: it answers with spoken replies, listens, and loops through the same brain as the web demo, then creates the lead and handoff note. To go live: buy a number at a provider (Twilio, or Exotel in India), set the number's "A call comes in" webhook to `https://aangan-desk.vercel.app/api/voice` and its status callback to `https://aangan-desk.vercel.app/api/voice?status=1`, and set `TWILIO_AUTH_TOKEN` on Vercel so only the provider can call it. Tested with `python3 -I tests/voice_sim.py` (simulated calls, no phone needed).

## What is not built (on purpose)

- A live phone number (needs a provider account and KYC). The demo uses the browser microphone; the phone endpoint is built and tested with simulated calls.
- WhatsApp and the web form (out of scope). The same engine would serve them.
- Any price quoting. See `/brief#cut`.

## Assumptions to confirm with Nikhil

Timeline hard stop of 6 weeks (services.md) vs 8–10 (qualified.md) · 500 sq ft commercial minimum (only said on call T18) · ₹10 per minute for phone and speech (placeholder, replace with a quote).
