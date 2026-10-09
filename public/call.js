// Live call simulator. The browser plays the caller; the server runs the agent (api/turn.py, api/finalize.py).
(function () {
  const $ = id => document.getElementById(id);
  const CRIT_NAMES = { 1: 'Real project, not just advice', 2: 'In Pune / PCMC', 3: 'Realistic timeline', 4: 'Budget band (never probed)', 5: 'Decision-maker' };
  const S = { transcript: [], facts: null, asked: {}, usage: { input: 0, output: 0 }, cost: 0, blocked: 0, started: null, live: false, busy: false, firstResp: null, model: '', timerId: null, hangAfter: null, scenario: null, last: null };

  let SCENARIOS = [];
  // ---------- UI helpers
  function addMsg(role, text) {
    const d = document.createElement('div');
    d.className = 'msg ' + role;
    const t = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    d.innerHTML = '<small>' + (role === 'agent' ? 'Aangan assistant' : role === 'caller' ? 'Caller' : '') + (role === 'sys' ? '' : ' · ' + t) + '</small>' + esc(text);
    if (role === 'sys') d.querySelector('small').remove();
    const log = $('log'); log.appendChild(d); log.scrollTop = log.scrollHeight;
  }
  function setStatus(t, live) { $('status').textContent = t; $('dot').classList.toggle('live', !!live); }
  function renderPanel(r) {
    const crit = r.decision && r.decision.criteria;
    if (crit) {
      $('crit').innerHTML = [1, 2, 3, 4, 5].map(k => {
        const c = crit[k] || { status: 'unclear', reason: '' };
        const cls = c.status === 'pass' ? 'good' : c.status === 'fail' ? 'bad' : 'mute';
        const lab = c.status === 'pass' ? 'Pass' : c.status === 'fail' ? 'Fail' : 'Open';
        return '<span class="n">' + k + '</span><span title="' + esc(c.reason) + '">' + CRIT_NAMES[k] + '<br><span class="muted small">' + esc(c.reason) + '</span></span><span class="pill ' + cls + '">' + lab + '</span>';
      }).join('');
    }
    const f = r.facts || {};
    const rows = [['Name', f.caller_name], ['Project', f.project_type && f.project_type.replace(/_/g, ' ')], ['Where', f.location_text], ['Size', f.area_sqft && f.area_sqft + ' sq ft'],
      ['Site', f.property_state], ['Timeline', f.timeline_text || (f.timeline_status !== 'unknown' ? f.timeline_status : null)], ['Budget said', f.budget_max_lakh ? (f.budget_min_lakh ? f.budget_min_lakh + '–' : 'up to ') + f.budget_max_lakh + ' lakh' : null],
      ['Decides', f.decision_maker && f.decision_maker.replace(/_/g, ' ')], ['Came via', f.referral_source], ['Asked price', f.asked_price ? 'yes (deflected)' : null]].filter(x => x[1]);
    $('facts').innerHTML = rows.length ? rows.map(x => '<dt>' + x[0] + '</dt><dd>' + esc(x[1]) + '</dd>').join('') : '<dt>Nothing yet</dt><dd>&nbsp;</dd>';
    $('tok').textContent = (S.usage.input + S.usage.output).toLocaleString('en-IN');
    $('cost').textContent = inr(S.cost, 3);
    $('blk').textContent = S.blocked;
  }

  // ---------- voice
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null, listening = false;
  function speak(text, cb) {
    if (!$('voiceOn').checked || !('speechSynthesis' in window)) return cb && cb();
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      const v = speechSynthesis.getVoices().find(x => /en[-_]IN/i.test(x.lang)) || speechSynthesis.getVoices().find(x => /^en/i.test(x.lang));
      if (v) u.voice = v;
      u.lang = (v && v.lang) || 'en-IN'; u.rate = 1.02;
      u.onend = () => cb && cb(); u.onerror = () => cb && cb();
      speechSynthesis.speak(u);
    } catch (e) { cb && cb(); }
  }
  function listen() {
    if (!SR || !S.live || S.busy || S.scenario) return;
    try {
      rec = new SR(); rec.lang = 'en-IN'; rec.interimResults = false; rec.maxAlternatives = 1;
      rec.onresult = e => { const t = e.results[0][0].transcript; listening = false; setMic(false); callerSays(t); };
      rec.onerror = () => { listening = false; setMic(false); };
      rec.onend = () => { listening = false; setMic(false); };
      rec.start(); listening = true; setMic(true);
    } catch (e) { setMic(false); }
  }
  function setMic(on) { $('micBtn').setAttribute('aria-pressed', on); $('micBtn').innerHTML = on ? '&#128308; Listening…' : '&#127908; Speak'; }

  // ---------- call flow
  async function startCall(scn) {
    if (S.live) return;
    Object.assign(S, { transcript: [], facts: null, asked: {}, usage: { input: 0, output: 0 }, cost: 0, blocked: 0, live: true, busy: true, scenario: scn || null, hangAfter: scn && scn.hangAfter || null, last: null });
    $('idle') && $('idle').remove(); $('log').innerHTML = ''; $('resultCard').hidden = true;
    $('startRow').hidden = true; $('liveRow').hidden = false;
    S.started = new Date(); const t0 = performance.now();
    setStatus('Ringing…', false); addMsg('sys', 'Call connected · ' + $('phoneNo').value);
    $('timer').textContent = '0:00';
    S.timerId = setInterval(() => { const s = Math.floor((Date.now() - S.started) / 1000); $('timer').textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }, 500);
    try {
      const r = await api('/api/turn', { transcript: [] });
      S.firstResp = Math.max(0.1, (performance.now() - t0) / 1000); S.model = r.model;
      S.transcript.push({ role: 'agent', text: r.reply }); addMsg('agent', r.reply); setStatus('Connected · answered in ' + S.firstResp.toFixed(1) + 's', true);
      S.busy = false; renderPanel(r);
      if (S.scenario) setTimeout(() => callerSays(S.scenario.open), 900); else speak(r.reply, listen);
    } catch (e) { addMsg('sys', 'Could not reach the agent: ' + e.message); endCall('caller'); }
  }

  async function callerSays(text) {
    text = (text || '').trim(); if (!text || !S.live || S.busy) return;
    S.busy = true; $('say').value = '';
    S.transcript.push({ role: 'caller', text }); addMsg('caller', text); setStatus('Assistant is thinking…', true);
    try {
      const r = await api('/api/turn', { transcript: S.transcript, facts: S.facts, asked: S.asked });
      S.facts = r.facts; S.asked = r.asked; S.last = r; S.model = r.model; if (r.llm_error && !S.warned) { S.warned = true; addMsg('sys', 'Note: the AI call failed (' + r.llm_error + '), so the rules-based fallback answered this turn.'); }
      S.usage.input += r.usage.input; S.usage.output += r.usage.output; S.cost += r.cost_inr; S.blocked += r.price_blocked ? 1 : 0;
      S.transcript.push({ role: 'agent', text: r.reply }); addMsg('agent', r.reply); renderPanel(r); setStatus('Connected', true);
      S.busy = false;
      const callerTurns = S.transcript.filter(m => m.role === 'caller').length;
      if (S.hangAfter && callerTurns >= S.hangAfter) { addMsg('sys', 'The line drops…'); return setTimeout(() => endCall('caller'), 700); }
      if (r.done) return speak(r.reply, () => setTimeout(() => endCall('agent'), 600));
      if (S.scenario) return setTimeout(() => callerSays(S.scenario.a[r.decision.ask] || "I'm not sure yet, can we sort that out at the consultation?"), 1100);
      speak(r.reply, listen);
    } catch (e) { S.busy = false; addMsg('sys', 'Error: ' + e.message); }
  }

  async function endCall(by) {
    if (!S.live) return; S.live = false; clearInterval(S.timerId); try { speechSynthesis.cancel(); rec && rec.abort(); } catch (e) {}
    $('liveRow').hidden = true; $('startRow').hidden = false; setStatus('Call ended', false); setMic(false);
    if (S.transcript.filter(m => m.role === 'caller').length === 0) { addMsg('sys', 'Hung up before speaking. No enquiry recorded.'); return; }
    addMsg('sys', 'Writing the handoff note…');
    try {
      const out = await api('/api/finalize', { transcript: S.transcript, facts: S.facts, phone: $('phoneNo').value, started_at: S.started.toISOString(), ended_at: new Date().toISOString(),
        ended_by: by, usage: S.usage, cost_inr: S.cost, model: S.model, price_blocked: S.blocked, first_response_secs: S.firstResp, demo: true });
      const lead = out.lead; if (!out.stored) saveLocalLead(lead);
      showResult(lead, out.stored);
    } catch (e) { addMsg('sys', 'Could not save the call: ' + e.message); }
    S.scenario = null;
  }

  function showResult(l, stored) {
    const tone = { qualified: 'good', callback: 'warn', escalated: 'bad', closed: 'mute' }[l.outcome];
    $('resultCard').hidden = false; $('resTitle').innerHTML = 'Result <span class="pill ' + tone + '">' + esc(l.label) + '</span>';
    let body = '';
    if (l.outcome === 'closed') {
      body = '<p class="small">No designer time spent. The caller was told kindly and honestly. Reason logged: <b>' + esc((l.reason || '').replace(/_/g, ' ')) + '</b>.' + ((l.reason === 'exploring_only' || l.reason === 'timeline_not_possible') ? ' Tagged <b>re-engage later</b>.' : '') + '</p>';
    } else {
      body = '<p class="small muted" style="margin-bottom:8px">This is the message a designer gets on Telegram:</p><div class="tg">' + esc((l.outcome === 'escalated' ? '🚨 ' : '') + l.note) + (l.outcome !== 'escalated' ? '<div class="btnrow">✅ I\'ll take it</div>' : '') + '</div>';
    }
    $('resBody').innerHTML = body;
    $('resFoot').textContent = (l.handoff && l.handoff.sent ? 'Delivered to the designers’ Telegram group. ' : l.outcome === 'closed' ? '' : 'Telegram is not connected yet, so this is a preview. ') + (stored ? 'Saved to the shared database.' : 'Saved in this browser (demo mode).');
    $('resultCard').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // ---------- wiring
  $('callBtn').onclick = () => startCall(null);
  $('hangBtn').onclick = () => endCall('caller');
  $('sendBtn').onclick = () => callerSays($('say').value);
  $('say').addEventListener('keydown', e => { if (e.key === 'Enter') callerSays($('say').value); });
  $('micBtn').onclick = () => { if (!SR) return alert('Voice input needs Chrome or Edge. You can type instead.'); if (listening) { try { rec.stop(); } catch (e) {} } else { try { speechSynthesis.cancel(); } catch (e) {} listen(); } };
  $('voiceOn').checked = LS.get('aangan_voice', false) && 'speechSynthesis' in window;
  $('voiceOn').onchange = e => LS.set('aangan_voice', e.target.checked);
  $('micNote').textContent = SR ? '' : 'Voice input is not supported in this browser; typing works.';
  function renderScenarios() { $('scenarios').innerHTML = '<span class="muted small" style="align-self:center">Watch a caller:</span>' + SCENARIOS.map((s, i) => '<button class="chip" data-i="' + i + '">' + esc(s.label) + '</button>').join(''); }
  fetch('/scenarios.json').then(r => r.json()).then(j => { SCENARIOS = j; renderScenarios(); }).catch(() => {});
  $('scenarios').onclick = e => { const b = e.target.closest('.chip'); if (b && !S.live) { $('voiceOn').checked = false; startCall(SCENARIOS[+b.dataset.i]); } };
  window.addEventListener('beforeunload', () => { try { speechSynthesis.cancel(); } catch (e) {} });

  api('/api/health').then(h => {
    const b = $('modeBanner');
    if (h.mode === 'live-ai') { b.className = 'banner ok'; b.textContent = 'Live AI on (' + h.model + '). Telegram handoff: ' + (h.telegram ? 'connected' : 'not connected, preview only') + '. Data: ' + (h.shared_database ? 'shared database' : 'this browser only') + '.'; }
    else { b.textContent = 'Demo mode: no AI key is set, so a rules-based assistant is answering. The qualification logic is identical; only the wording is simpler. Add an API key on Vercel to switch the AI on.'; }
  }).catch(() => { $('modeBanner').textContent = 'Could not check setup.'; });
})();
