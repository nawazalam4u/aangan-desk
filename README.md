# Aangan Desk

An AI phone assistant for Aangan Studio (MESA Case 03). It answers every incoming enquiry call instantly, qualifies the caller with Nikhil's five-criteria rubric, never quotes a price, and sends the designer a complete handoff note on Telegram. A dashboard shows volume, response time, cost and the pipeline it creates.

**Pages:** `/` live call simulator · `/dashboard` Nikhil's dashboard · `/brief` automation brief, Nine Checks, the Cut, components map, red flags.

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
```

## Turn things on (Vercel > Settings > Environment Variables)

| Variable | What it switches on |
|---|---|
| `GEMINI_API_KEY` | The real AI (Gemini 3.1 Flash-Lite, with 3.5 Flash as backup). Or `ANTHROPIC_API_KEY` for Claude Haiku 5.5. Check `/api/health?probe=1`. |
| `TELEGRAM_BOT_TOKEN` | Handoff notes to the designers' private group, with an "I'll take it" button. Send `/register <dashboard key>` in the group to choose where notes go. |
| `TELEGRAM_WEBHOOK_SECRET` | Makes the button work (point the bot webhook to `/api/telegram` with the same secret) |
| `DATABASE_URL`, `DASHBOARD_KEY` | Shared Neon Postgres database (the table is created automatically) so the dashboard shows every call, locked by a key |

Without a database the dashboard shows calls made in the same browser. With the database set but no `DASHBOARD_KEY`, the dashboard stays locked on purpose, because it holds callers' phone numbers.

## What is not built (on purpose)

- A real phone number and telephony. The demo uses the browser microphone; a voice provider replaces only the voice layer.
- WhatsApp and the web form (out of scope). The same engine would serve them.
- Any price quoting. See `/brief#cut`.

## Assumptions to confirm with Nikhil

Timeline hard stop of 6 weeks (services.md) vs 8–10 (qualified.md) · 500 sq ft commercial minimum (only said on call T18) · ₹10 per minute for phone and speech (placeholder, replace with a quote).
