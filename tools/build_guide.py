from docx import Document
from docx.shared import Pt, Inches
d = Document(); d.styles['Normal'].font.name = 'Calibri'; d.styles['Normal'].font.size = Pt(11)
for s in d.sections: s.left_margin = s.right_margin = Inches(0.9)
H = lambda t, l=1: d.add_heading(t, level=l)
def P(t, b=False): r = d.add_paragraph().add_run(t); r.bold = b
def B(t): d.add_paragraph(t, style='List Bullet')
def N(t): d.add_paragraph(t, style='List Number')
d.add_heading('Aangan Desk: the study guide', 0)
P('Everything about this project, explained from zero. Read it once, then use the questions at the end to practise.', True)
P('Live app: https://aangan-desk.vercel.app    Code: https://github.com/nawazalam4u/aangan-desk')

H('1. The story in one minute')
P("Aangan Studio is an interior design company in Pune. About 200 people a month enquire, mostly by phone. Nearly half (48%) never get an answer within two days, and a third call when the office is closed. The owner, Nikhil, found that people who get an answer within an hour are four times more likely to become customers. So we built an AI phone assistant that answers instantly, any hour; asks the few questions that matter; decides whether the caller is worth a designer's time using Nikhil's own rules; and sends the designer a complete note so nobody asks the same questions twice. It saves every call, shows Nikhil a dashboard (numbers and cost), and puts each good lead into HubSpot, a CRM, so the sales team can follow it up.")
P('One thing we deliberately did NOT build: the assistant never quotes prices. Nikhil asked for it, but his own pricing guide says no number may ever be quoted (prices depend on the site). Spotting and respecting that is the most important judgement in the project.')

H('2. Words you need to know (plain English)')
for a, b in [
 ('AI / LLM (large language model)', 'A program trained on huge amounts of text that can read and write language. We used Google Gemini. Think of it as a very well-read assistant that can understand what a caller says.'),
 ('Prompt', 'The instructions we give the AI ("you are a polite receptionist, never say a price"). Like a job description.'),
 ('API', 'A way for one program to ask another program to do something over the internet. Our app asks Gemini, Telegram and HubSpot to do things through their APIs. Like ordering at a restaurant: you ask the waiter (API), the kitchen (the service) does the work.'),
 ('API key / token', 'A secret password that proves it is really us making the request. Never share it or put it on GitHub. That is why we keep them in Vercel\'s hidden settings.'),
 ('Front end / back end', 'Front end = what you see and click in the browser (our web pages). Back end = the hidden code on a server that does the work (our /api programs).'),
 ('Database (Neon)', 'A place that remembers things after the program stops. Every call is stored here. Without it, the dashboard would have nothing to show. Neon is a database service in the cloud; Postgres is the type of database.'),
 ('Server / serverless', 'A server is a computer that is always on, running your code. "Serverless" (what Vercel gives us) means we do not look after any computer: our code wakes up when needed and sleeps otherwise.'),
 ('Git and GitHub', 'Git is a time machine for code: it saves every version so you can go back. GitHub is a website that stores that history online, safely, and lets others see it. Our repo is public, so it works like your portfolio.'),
 ('Vercel and deploying', 'Deploying means putting your app on the internet so anyone can open it. Vercel does that for us. We linked GitHub to Vercel, so each time new code is saved to GitHub, Vercel republishes the website automatically.'),
 ('Webhook', 'A web address that another service calls when something happens. Example: when a designer taps a button in Telegram, Telegram calls our webhook to tell us. A real phone company would call our /api/voice webhook for every call.'),
 ('Environment variable', 'A secret setting stored outside the code (keys, passwords). Our code reads them when it runs.'),
 ('Telegram bot', 'A small automatic account on Telegram that our app controls. It posts the designer note and shows the "I\'ll take it" button.'),
 ('CRM and HubSpot', 'CRM = customer relationship manager: a tool that keeps one record per customer with every call, note and follow-up, and tracks deals from "new" to "won". HubSpot is the CRM our course uses.'),
 ('Guardrail', 'A safety rule that stops the AI doing something it must never do. Ours stops any price being spoken.')]:
    B(a + ': ' + b)

H('3. What happens during one call (the flow)')
for t in ['A customer calls (in the demo, you speak into your browser microphone; in real life a phone provider connects the call).',
 'The caller\'s words become text.',
 'Our back end sends that text to the AI (Gemini) and asks only for FACTS: what area, what size, when do they need it, are they the decision-maker.',
 'Our own code (not the AI) checks Nikhil\'s five rules: Is it a real project, in Pune/PCMC, with a realistic timeline, a sensible budget, and is the decision-maker on the call? The result is one of four things: ask another question, close politely, escalate to a senior person, or send to a designer.',
 'The AI writes a friendly reply for what the code decided. A price filter checks the reply, so no price can leave.',
 'The reply is spoken. This repeats until the call ends.',
 'At the end, the lead is saved in Neon, the note is posted to Telegram (a designer taps "I\'ll take it"), and the lead is created in HubSpot (contact, note, task, deal).',
 'The dashboard reads Neon and shows Nikhil everything: how many calls, how fast, outcomes, cost, and whether a designer has claimed each lead.']: N(t)

H('4. How everything is connected')
for t in ['GitHub holds the code  ->  Vercel publishes it as the website and runs the back end.',
 'Vercel talks to: Gemini (the AI), Neon (memory), Telegram (designer alerts), HubSpot (CRM).',
 'Each connection uses a secret key stored in Vercel\'s settings, never in the code.',
 'The "How it connects" page (/connect) shows a live green light for each one, with test buttons.']: B(t)

H('5. Why HubSpot is in the project')
P("HubSpot is the CRM, the long-term memory of each customer relationship. Our own database and dashboard answer 'how is the assistant doing?' (calls, speed, cost). HubSpot answers 'what is happening with each customer?' A lead does not end when the call ends: a designer visits, sends a proposal, the client thinks, someone follows up. After every qualified, call-back or escalated call we automatically create in HubSpot: a contact (matched by phone number so repeat callers are one record), the full handoff note, a call-back task, and a deal in the first stage of the sales pipeline. Callers who are not a fit are never sent, so the CRM stays clean. If HubSpot is down, everything else still works. We verified it on the real account: a test call produced the contact, deal, note and task, and HubSpot even wrote its own AI summary of the lead.")

H('6. The design idea that makes it good')
P('The AI talks; code decides.', True)
P("We do not let the AI decide who is a good lead or what it may say. The AI is great at understanding messy human speech but can make mistakes. So the AI only extracts facts and words the reply, and plain code applies the rules. Benefits: (1) we can test the rules against all 40 real enquiries, (2) Nikhil can change a rule without rewriting a prompt, (3) the price rule cannot be talked around, because a filter in code checks every reply. We also added a safety net: the AI cannot close a call unless the caller's own words support it. We found this need by testing: the AI once called an office 'out of scope' and once treated a possession date as a deadline; both would have wrongly turned away good customers.")

H('7. The Nine Checks, simply')
for t in ['Kill switches (any NO = do not build): 1 Problem real, 2 Workflow repeated, 3 Input available. All yes.',
 'Sizing (any NO = build something smaller): 4 Output valuable, 5 Impact measurable, 8 ROI worth it. All yes.',
 'Boundary (any NO = the AI builds the tool, a human stays in charge): 6 Failure risk OK, 7 Judgment protected, 9 Owner clear. Check 6 failed for pricing, because a wrong price on an Rs 8-14 lakh job cannot be undone. That is THE CUT: the one thing Nikhil asked for that a check stops us building.']: B(t)

H('8. How we tested it')
for t in ['All 40 real enquiries run through the rules: they agree on 40 of 40.',
 'The same enquiries through the real AI: 39 of 39 testable agree (we fixed two real mistakes found this way).',
 '9 demo calls on the live AI, run twice; price-trick attacks ("is it 2000 per sq ft?"): zero leaks.',
 'Hindi and Marathi calls; a Hindi complaint correctly escalates.',
 'Simulated phone calls through the phone endpoint; HubSpot requests tested against a fake HubSpot, then a real one.',
 'Live end-to-end: call -> Telegram -> Neon -> HubSpot -> dashboard.']: B(t)

H('9. Honest limits (say these before the professor finds them)')
for t in ['No real phone number is attached. It needs a provider account (Twilio or Exotel) and Indian KYC. The demo uses the browser microphone; the phone endpoint is built and tested with simulated calls.',
 'The cost of phone and speech (Rs 10 a minute) is an assumption; the AI cost is measured (about Rs 0.4 a call).',
 'Two rules need Nikhil to confirm: the 6-week timeline limit and the 500 sq ft commercial minimum.',
 'The 4x conversion number is a correlation, not proof that speed causes sales.',
 'WhatsApp and the web form are not built (out of scope), but the same engine would serve them.']: B(t)

H('10. Questions your professor may ask, with answers')
QA = [
 ('What problem does this solve?', 'Half of enquiries get no reply in 48 hours and a third arrive after hours; fast replies convert 4x better. The assistant answers instantly, qualifies, and gives designers a full note.'),
 ('Why did you not quote prices when the founder asked?', "His own pricing guide forbids any number because prices vary by site (a standard vs premium kitchen can be 3x). A wrong number on an Rs 8-14 lakh decision cannot be taken back. Check 06 fails, so a human (the designer) keeps pricing. We deflect politely and still book the consultation; two September callers who were deflected still booked."),
 ('Where is the AI and what does it do?', 'Gemini 3.1 Flash-Lite extracts facts from the caller\'s words and writes the replies. It does not make decisions.'),
 ('Why not let the AI decide everything?', 'AI can be wrong and cannot be tested rule by rule. Rules in code are predictable, testable against real data and changeable by the founder. We found real AI mistakes in testing and added a safety net.'),
 ('How do you stop it quoting a price?', 'Two layers: instructions to the AI, and a code filter on every reply that blocks rupee amounts, "lakh", "per sq ft" and Hindi/Marathi equivalents. We attacked it with trick questions: zero leaks.'),
 ('Why Telegram and not email?', 'Designers are on sites; a push alert is seen in seconds, email later. The "I\'ll take it" button prevents two designers calling the same person and lets us measure claim time. Email has no claim button and needs a verified domain. The record is also kept in the database and HubSpot.'),
 ('Why HubSpot?', 'It is the CRM: it tracks each customer and deal after the call. Our dashboard measures the assistant; HubSpot manages the relationships.'),
 ('What is the database for?', 'Memory. Neon stores every call so the dashboard can show history and cost. Chosen because the Supabase free slots were full and Neon is free and fast.'),
 ('What are GitHub and Vercel doing?', 'GitHub stores and versions the code. Vercel publishes it and runs the back end. They are linked, so saving to GitHub republishes the site automatically.'),
 ('How is it kept secure?', 'Secret keys live in Vercel\'s hidden settings, not the code; the dashboard is locked with a key because it holds phone numbers; inputs are length-limited; the phone endpoint can verify requests really come from the phone provider; the Telegram group must be private.'),
 ('How much does it cost to run?', 'About Rs 0.4 a call for the AI (measured) plus an assumed Rs 46 a call for phone and speech: about Rs 9,000 a month at 200 calls. One extra Rs 8-14 lakh project pays for about a year.'),
 ('Does this replace the front desk?', 'No. It removes the unanswered and unrecorded calls. People still run consultations, calendars and relationships.'),
 ('How would you extend it to WhatsApp or the web form?', 'The rules, filter, note, CRM sync and dashboard do not care about the channel. WhatsApp would call the same turn endpoint; the form is a one-shot version. We already tested all 20 of those enquiries through the rules.'),
 ('What happens if the AI or a service is down?', 'If the AI fails the rules-based fallback answers; if HubSpot fails the call, Telegram note and dashboard still work; a dropped call becomes a call-back lead.'),
 ('What is the biggest risk?', 'Wrongly turning away a good customer. So the code only closes a call on clear evidence, borderline cases are asked or forwarded, and every closed call is listed on the dashboard for Nikhil to review.'),
 ('What would you do next?', 'Attach a real phone number, confirm the two rules with Nikhil, add an automatic nudge when a lead is unclaimed after 15 minutes, and add WhatsApp.'),
 ('Can I see it working?', 'Open the live app, press "Qualified home", then show the dashboard, the Telegram message and the HubSpot contact.')]
for q, a in QA:
    P('Q: ' + q, True); P('A: ' + a)

H('11. How to demo it in 3 minutes')
for t in ['Open the live app. Say what the problem is (48% unanswered).', 'Press "Qualified home" and watch the five checks go green; point out that it refused to give a price.', 'Show the Telegram message and tap "I\'ll take it".', 'Open HubSpot Contacts and show the new lead with its deal and task.', 'Open the dashboard (key box on the page) and show cost per call and the chart.', 'Open /brief and show The Cut and the components map.']: N(t)
d.save('docs/Aangan_Desk_Study_Guide.docx'); print('saved')
