"""Builds docs/Case03_Aangan_Submission.docx (needs python-docx). Run from the aangan-desk folder."""
from docx import Document
from docx.shared import Pt, Inches
d = Document()
d.styles['Normal'].font.name = 'Calibri'; d.styles['Normal'].font.size = Pt(10.5)
for s in d.sections: s.left_margin = s.right_margin = Inches(0.8); s.top_margin = s.bottom_margin = Inches(0.7)
h = lambda t, l=1: d.add_heading(t, level=l)
def p(t, b=False): r = d.add_paragraph().add_run(t); r.bold = b
def bl(t): d.add_paragraph(t, style='List Bullet')
d.add_heading('Case 03: Nikhil, Unanswered Enquiries', 0)
p("MESA AI and its Application · Founder's Office · Cohort C4 · Nawaz Alam")
p('Live app: https://aangan-desk.vercel.app', True)
p('Dashboard: https://aangan-desk.vercel.app/dashboard · How it connects (incl. HubSpot explained): https://aangan-desk.vercel.app/connect · Full write-up: https://aangan-desk.vercel.app/brief')
p('Code (public): https://github.com/nawazalam4u/aangan-desk (linked to Vercel: every push redeploys)')
p('Try it: open the live app and press a scenario button, for example "Qualified home". Watch the call, the five checks and the Telegram handoff note appear. The caller language can be English, Hindi or Marathi.')

h('1. Automation Brief')
p('Pain', True); p("About 200 enquiries a month and roughly 48% get no reply within 48 hours (about 96 a month). A third arrive outside the 10am-7pm front desk. Nikhil's numbers: an answer inside an hour converts at 4x the next-day rate, and the average project is Rs 8-14 lakh. Enquiries that do reach a designer arrive as forwarded messages with no context, so the first call re-asks what the desk already asked. September phone evidence: T08 missed at 10:47pm; T16 called Monday and was never logged; T07 hung up before details were taken; T17 line dropped.")
p('User', True); p("The caller (a first-time Pune/PCMC enquirer who talks to the assistant); the 14 designers who receive the handoff note; Nikhil, who owns the rules and reads the dashboard. The 2-person front desk is not replaced.")
p('Outcome', True)
for t in ['100% of calls answered in under 5 minutes, day or night (the assistant answers on the first ring)', '0 calls lost to process (missed, unlogged, no details)', 'Every qualified lead reaches a designer, and the CRM, in under 5 minutes with all the basics, so no repeat questions', '0 prices quoted', 'Cost per call and per qualified lead visible on the dashboard']: bl(t)
p('The journey today (phone)', True)
for t in ['Caller rings the studio number.', 'Outside 10am-7pm the phone rings out (T08, 10:47pm, no voicemail, call-back unanswered).', 'The desk asks questions in an inconsistent order; size, timeline and ownership are sometimes skipped.', "Notes are inconsistent: T16 'I don't see a note'; T07 no name or number taken.", "The desk decides alone who is worth a designer, from memory of Nikhil's rubric.", 'The lead is forwarded to a designer as a message with no context; booking waits for the calendar (T12).', 'The designer re-asks the same questions; Nikhil has no numbers until he pulls them by hand.']: d.add_paragraph(t, style='List Number')

h('2. The Nine Checks')
rows = [('01 Problem Real', 'Pass', "48% unanswered in 48 hours and a 4x conversion gap (Nikhil's own pull); T08, T16, W02, W08 show it live."),
('02 Workflow Repeated', 'Pass', '~200 enquiries a month; 20 of the 40 September transcripts are phone calls asking the same five questions.'),
('03 Input Available', 'Pass', 'The 40 transcripts, services.md, qualified.md and pricing.md exist today. Caveat: the live phone line (number, telephony, speech) is an integration not included in the demo, which uses the browser microphone.'),
('04 Output Valuable', 'Pass', 'Designers act on a complete note; the sales team works the lead in HubSpot; Nikhil acts on the dashboard; callers get an answer at 11pm instead of nothing.'),
('05 Impact Measurable', 'Pass', 'Time to answer, outcome, time to Telegram, time to designer claim, minutes and AI cost are logged for every call.'),
('08 ROI Worth It', 'Pass', 'AI step about 5 paise per turn (about Rs 0.4 per call, measured on 39 real enquiries); with an assumed Rs 10/min phone and speech layer about Rs 46 per call, about Rs 9,000 a month at 200 calls. One extra Rs 8-14 lakh project covers about a year. The voice price is an assumption.'),
('06 Failure Risk OK', 'No for pricing', 'A wrong number on a Rs 8-14 lakh decision anchors the customer and cannot be taken back (T13: a standard vs premium kitchen alone can be 3x). Every other failure is recoverable and logged.'),
('07 Judgment Protected', 'Pass', 'The assistant only forwards. The designer owns the price, the consultation and the fit; senior staff own complaints (T09). Nothing is booked, promised or quoted by the AI.'),
('09 Owner Clear', 'Pass', 'Nikhil owns qualified.md; the rules in code mirror it; the dashboard lists every closed call so he can catch a good lead declined by mistake.')]
t = d.add_table(rows=1, cols=3); t.style = 'Light Grid Accent 1'
for i, x in enumerate(['Check', 'Result', 'Evidence from the case']): t.rows[0].cells[i].text = x
for a, b, c in rows:
    r = t.add_row().cells; r[0].text = a; r[1].text = b; r[2].text = c
for row in t.rows:
    row.cells[0].width = Inches(1.5); row.cells[1].width = Inches(0.9); row.cells[2].width = Inches(4.5)

h('The Cut: quoting per-square-foot pricing')
p('Nikhil asked: "the system should be able to quote our standard per-square-foot pricing so people don\'t have to wait for that."')
p('The check that stops it: Check 06, Failure Risk (with 07 behind it). pricing.md is headed "indicative only, varies by site" and says no number from the guide should ever be quoted; it lists what the agent must never say.')
p('What I built instead: the assistant answers a price question with the approved line ("Pricing depends on the site, the materials you choose, and the scope... your designer will walk you through it"), once, and keeps going. Asking for a price never disqualifies a caller. T02 and T13 asked twice, were deflected and still booked.')
p('Enforced in code, not only in a prompt: every reply passes a filter that blocks rupee figures, "lakh", "per sq ft" and the Hindi/Marathi equivalents. In testing, every leak attempt was blocked and three live tricks on the real AI produced no price.')

h('3. Components Map')
p('Trigger > Input > Context > Processing > AI > Output. Dots mark handoffs; red cells are the human gate.')
d.add_picture('docs/components-map.png', width=Inches(6.9))

h('Why HubSpot is part of this project')
p("HubSpot is the CRM: the system of record for each lead after the call. The assistant writes every qualified, call-back or escalated lead into HubSpot as a contact (matched on phone number so a repeat caller is one record), with the full handoff note on its timeline, a call-back task, and a deal in the first pipeline stage. Designers and Nikhil then work the relationship in HubSpot and move the deal toward won or lost.")
p("Our own database and dashboard answer a different question: how is the phone assistant performing (volume, speed, cost)? HubSpot answers: what is happening with each customer? Callers who are not a fit are never sent to the CRM, no price is ever written to it, and if HubSpot is down the call, the Telegram note and the dashboard still work.")

h('Telegram or email for the handoff?')
p("Telegram, with the database and HubSpot as the permanent record. A push alert reaches a designer on site within the 5-minute promise; the \"I'll take it\" button stops two designers calling the same person and the claim time is measured; no designer-specialty data exists so a shared group beats picking an inbox; a bot is free and instant with no spam-folder risk. Weakness covered: Telegram is not a system of record, so every note is also stored in the database; the group must be private because it contains callers' numbers. I would switch to email if designers will not install Telegram or compliance requires it.")

h('Red flags found')
for x in ['The ask contradicts pricing.md (see The Cut).', 'A real phone number is not included: it needs telephony, KYC and speech. The demo runs the full logic through the browser microphone; a provider replaces only the voice layer.', 'services.md says under 6 weeks cannot start; qualified.md says 8-10 weeks. I used 6 as the hard stop and flag under 12 weeks. Nikhil to confirm.', 'A 500 sq ft commercial minimum appears only in call T18, not in services.md. Implemented as one soft rule; Nikhil to confirm.', 'The rubric has no category for angry existing clients (T09). I added an escalation path.', 'Recording and consent: the greeting says it is an AI and the call is recorded; the Telegram group must be private.', 'The 5-minute promise stops at Telegram if no designer claims the lead; the dashboard now flags any lead unclaimed after 15 minutes.', 'The "4x conversion" figure is a correlation; I did not promise a lift.', 'The brief names "Arjun" (the founder is Nikhil); the zip had no enquiries/ folder, only one PDF, which I used in full.']: bl(x)

h('How it was tested')
for x in ["The 40 real September enquiries run through the rules: all agree with my reading of Nikhil's rubric.", "The same enquiries through the real AI (Gemini 3.1 Flash-Lite): 39 of 39 testable agree. Two real errors were found and fixed (an office wrongly called out of scope; a possession date read as a deadline) and a safety net was added so the AI cannot close a lead without the caller's own words backing it.", 'All 9 demo calls pass on the live AI, run twice; Hindi and Marathi calls tested (including a Hindi complaint that escalates). Price-leak attacks: 0 leaks.', 'HubSpot sync tested against a simulated HubSpot (contact created once, repeat caller matched, note, task and deal sent correctly); to be confirmed against a real account.', 'Live deployment tested end to end: call, handoff note to Telegram, record in the Neon database, protected dashboard, auto-deploy from GitHub.']: bl(x)

h('How this extends to WhatsApp and the web form (not built)')
p('The rules engine, price guardrail, note, CRM sync and dashboard are channel-free. A WhatsApp message would call the same turn endpoint and the form is a single-shot version of the same extraction. All 10 WhatsApp and 10 form enquiries were already run through the rules as a test. In September, 2 of 10 WhatsApp threads sat unanswered for 2-4 days, 5 more waited 16+ hours, and the form enquiries have no recorded response times.')
d.save('docs/Case03_Aangan_Submission.docx'); print('saved')
