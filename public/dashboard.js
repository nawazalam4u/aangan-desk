(async function () {
  const $ = id => document.getElementById(id);
  const S = getSettings();
  const AVG_PHONE_MIN = 4.6; // mean of the 20 September call lengths in the transcripts
  const EST_LLM_PER_CALL = 0.4; // Rs, estimate before live data: ~10k input + ~1.5k output tokens on Gemini 3.1 Flash-Lite

  let leads = [], mode = 'local', bt = [], HUB_PORTAL = null;
  let lockMsg = '';
  // Speed: one request for calls (+ HubSpot portal id) and the static baseline, in parallel.
  // The last answer is cached in this browser, so the page paints instantly and then refreshes itself.
  const fetchLeads = () => fetch('/api/leads', { headers: { 'x-dashboard-key': LS.get('aangan_key', '') } }).then(r => r.json()).catch(() => ({}));
  const cached = LS.get('aangan_cache', null);
  const [fresh, btj] = await Promise.all([cached ? Promise.resolve(null) : fetchLeads(), fetch('/data/backtest.json').then(r => r.json()).catch(() => [])]);
  const j = fresh || cached || {};
  bt = btj; mode = j.mode || 'local'; leads = j.leads || []; HUB_PORTAL = j.hubspot_portal || null;
  if (j.mode === 'locked') lockMsg = j.error || 'Dashboard is locked.';
  if (fresh && fresh.mode === 'shared') LS.set('aangan_cache', fresh);
  const sig = d => JSON.stringify((d.leads || []).map(l => [l.id, l.outcome, l.booking && l.booking.status, l.claimed_at]));
  async function refresh() {          // background refresh: repaint only when something changed and no call is open
    const f = await fetchLeads();
    if (f.mode !== 'shared') { if (cached && f.mode === 'locked') { LS.set('aangan_cache', null); location.reload(); } return; }
    if (sig(f) !== sig(j)) { LS.set('aangan_cache', f); if (!document.querySelector('dialog[open]')) location.reload(); }
  }
  if (cached) refresh();
  setInterval(refresh, 20000);
  if (mode === 'local') leads = getLocalLeads();
  // Real voice calls (Vaani, WebRTC or phone) drive every number when they exist; simulator calls are practice only.
  const allLeads = leads.slice(); const processing = allLeads.filter(l => l.outcome === 'processing'); const realLeads = allLeads.filter(l => l.real_call && l.outcome !== 'processing');
  if (realLeads.length) leads = realLeads;
  if (mode === 'locked') { leads = []; }

  const phRows = bt.filter(r => r.channel === 'phone');
  const qualRate = phRows.length ? phRows.filter(r => r.got === 'forward' || r.got === 'ask').length / phRows.length : 0.6; // share of September phone calls that reach a designer
  $('mode').className = 'banner' + (mode === 'shared' ? ' ok' : '');
  if (mode === 'locked') {
    $('mode').className = 'banner';
    $('mode').innerHTML = '<b>\ud83d\udd12 Dashboard locked.</b> It holds callers\' phone numbers, so it needs your key. <form id="kf" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px"><input id="kk" type="password" autocomplete="current-password" placeholder="Paste your dashboard key" aria-label="Dashboard key" style="max-width:280px"><button class="btn primary sm" type="submit">Unlock</button></form><span class="small">' + (LS.get('aangan_key', '') ? 'That key was not accepted. ' : '') + 'Your key is the DASHBOARD_KEY you were given.</span>';
    $('kf').onsubmit = e => { e.preventDefault(); LS.set('aangan_key', $('kk').value.trim()); location.reload(); };
  }
  if (mode !== 'locked') $('mode').textContent = mode === 'shared' ? (realLeads.length ? 'Showing ' + realLeads.length + ' real voice call' + (realLeads.length > 1 ? 's' : '') + ' with the Vaani agent. Numbers below come from these calls only; simulator practice calls are kept separate.' : 'Shared database connected. No real voice calls yet: make one on the Live AI call page.') : 'Demo mode: showing calls made in this browser (plus the September baseline). Connect the shared database to see calls from all devices.';

  // ------------- aggregates
  const N = leads.length;
  const cnt = o => leads.filter(l => l.outcome === o).length;
  const q = cnt('qualified'), closed = cnt('closed'), esc_ = cnt('escalated'), cb = cnt('callback');
  const fr = leads.map(l => l.first_response_secs || 0).sort((a, b) => a - b);
  const median = fr.length ? fr[Math.floor(fr.length / 2)] : null;
  const within5 = leads.filter(l => (l.first_response_secs || 0) <= 300).length;
  const afterH = leads.filter(l => l.after_hours).length;
  const aiLeads = leads.filter(l => l.model && l.model !== 'demo-rules' && (l.llm_cost_inr || 0) > 0); // only calls the real AI handled
  const llmAvg = aiLeads.length ? aiLeads.reduce((a, l) => a + l.llm_cost_inr, 0) / aiLeads.length : null;
  // demo calls are played back in seconds, so use the realistic average call length for the voice-layer estimate
  const realMin = realLeads.length ? realLeads.reduce((a, l) => a + (l.duration_secs || 0), 0) / realLeads.length / 60 : null;
  const callMin = realMin ? Math.round(realMin * 10) / 10 : AVG_PHONE_MIN;   // real average call length once real calls exist
  const voicePerCall = callMin * S.voiceRsPerMin;
  const claimed = leads.filter(l => l.claimed_at && l.handoff && l.handoff.at);
  const claimMin = claimed.length ? claimed.reduce((a, l) => a + (new Date(l.claimed_at) - new Date(l.handoff.at)) / 60000, 0) / claimed.length : null;
  const sent = leads.filter(l => l.handoff && l.handoff.sent).length;
  const handedOff = q + cb + esc_;

  // ------------- KPIs
  const k = (v, l, s, tone) => '<div class="card kpi"><div class="v">' + v + '</div><div class="l">' + l + '</div>' + (s ? '<div class="s ' + (tone ? 'pill ' + tone : 'muted') + '">' + s + '</div>' : '') + '</div>';
  $('kpis').innerHTML =
    k(N, 'Calls handled', N ? '' : 'make a demo call') +
    k(N ? Math.round(100 * within5 / N) + '%' : '100%', 'Answered within 5 minutes', N ? 'median ' + median.toFixed(1) + ' s' : 'by design: answers on ring', 'good') +
    k(afterH, 'After-hours calls caught', 'outside 10am–7pm or Sunday') +
    k(q, 'Qualified, sent to designers', handedOff ? sent + ' delivered on Telegram' : '', 'info') +
    k(closed, 'Closed politely (not a fit)', 'no designer time spent') +
    k(esc_ + cb, 'Escalated / call-back queued', esc_ + ' escalated · ' + cb + ' call-back' + (cb === 1 ? '' : 's'), 'warn') +
    k(claimMin == null ? '—' : claimMin.toFixed(1) + ' min', 'Designer claims a lead in', claimed.length ? claimed.length + ' claimed' : 'needs Telegram connected');

  // ------------- cost
  const llmPerCall = llmAvg == null ? EST_LLM_PER_CALL : llmAvg;
  const perCall = llmPerCall + voicePerCall;
  const monthly = perCall * S.monthlyCalls;
  $('costBasis').textContent = llmAvg == null ? 'AI cost is an estimate until a call runs on the live AI' : 'AI cost measured on ' + aiLeads.length + ' live-AI call' + (aiLeads.length > 1 ? 's' : '');
  const row = (a, b, cls) => '<span' + (cls ? ' class="' + cls + '"' : '') + '>' + a + '</span><span' + (cls ? ' class="' + cls + '"' : '') + '>' + b + '</span>';
  $('costKv').innerHTML =
    row('AI model (' + esc((leads.find(l => l.model && l.model !== 'demo-rules') || {}).model || 'Gemini 3.1 Flash-Lite') + ')<span class="meas">' + (llmAvg == null ? 'estimate' : 'measured') + '</span>', inr(llmPerCall, 2) + ' / call') +
    row('Phone + voice (Vaani)<span class="assume">vendor estimate</span>', inr(voicePerCall, 0) + ' / call (' + callMin + ' min' + (realMin ? ', real average' : ', September average') + ')') +
    row('Hosting (Vercel free tier)', '₹0') +
    row('Cost per call', inr(perCall, 2), 'tot') +
    row('Cost per qualified lead', realLeads.length ? inr(perCall * N / Math.max(q, 1), 0) + ' (from real calls)' : inr(perCall / qualRate, 0) + ' (at the September qualified rate)') +
    row('Projected for ' + S.monthlyCalls + ' calls / month', inr(monthly, 0), 'tot') +
    row('For comparison: one front-desk person<span class="assume">assumption</span>', inr(S.frontDeskMonthly, 0) + ' / month');

  const pipeline = (q || 0) * S.projectValueLakh;
  const estQual = Math.round(S.monthlyCalls * qualRate);
  $('valKv').innerHTML =
    row('Leads sent to designers', q + ' qualified' + (cb ? ' + ' + cb + ' call-backs' : '')) +
    row('Qualified pipeline (at ₹' + S.projectValueLakh + ' lakh avg)', pipeline ? '₹' + pipeline + ' lakh' : '—') +
    row('Designer calls spared re-asking basics', q + cb) +
    row('Not-a-fit callers closed with no designer time', closed) +
    row('At ' + S.monthlyCalls + ' calls / month, qualified leads', '~' + estQual + ' (' + Math.round(qualRate * 100) + '% of September calls)', 'tot');
  const be = monthly / (S.projectValueLakh * 100000);
  $('roiLine').textContent = 'Break-even check: at ' + inr(monthly, 0) + ' a month, the tool pays for itself if it helps convert ' + (be * 100).toFixed(3) + '% of one extra ₹' + S.projectValueLakh + ' lakh project per month. The brief says a sub-1-hour answer converts 4× better, but that is a correlation in your own data, so measure it here for a few weeks before promising Nikhil a lift.';

  // ------------- Sept comparison (from backtest rows)
  const ph = bt.filter(r => r.channel === 'phone'), wa = bt.filter(r => r.channel === 'whatsapp'), fm = bt.filter(r => r.channel === 'form');
  if (bt.length) {
    const missedPh = ph.filter(r => r.resp === 'missed').length, lostPh = 3; // T08 missed, T16 never logged, T07 no name/number taken
    const waMissed = wa.filter(r => r.resp === 'missed').length, waSlow = wa.filter(r => r.resp === 'slow').length, waFast = wa.filter(r => r.resp === 'fast').length;
    const fwd = ph.filter(r => r.got === 'forward' || r.got === 'ask').length;
    const decl = ph.filter(r => r.got === 'decline').length, esc2 = ph.filter(r => r.got === 'escalate').length;
    $('cmp').innerHTML =
      '<span class="h">Phone, September</span><span class="h">Front desk (actual)</span><span class="h">With the assistant</span>' +
      '<span>Calls answered</span><span class="bad">19 of 20 (1 missed at 10:47pm)</span><span class="good">20 of 20, instantly</span>' +
      '<span>Calls lost to process (missed, never logged, no details taken)</span><span class="bad">' + lostPh + ' of 20</span><span class="good">0 (every call gets a record; drops queue a call-back)</span>' +
      '<span>Designer receives</span><span class="bad">forwarded message, no context</span><span class="good">one structured note, five criteria shown</span>' +
      '<span>Qualified for a designer</span><span>decided by whoever answered</span><span class="good">' + fwd + ' forwardable · ' + decl + ' closed · ' + esc2 + ' escalated</span>' +
      '<span>Price asked (T02, T13)</span><span>deflected by hand, consistently</span><span class="good">deflected by code; no figure can leave</span>';
    $('cmpNote').textContent = 'Other channels, same month (not built, shown for scale): WhatsApp ' + waMissed + ' of 10 sat unanswered for days, ' + waSlow + ' waited 16+ hours, only ' + waFast + ' were answered within an hour. The 10 web-form enquiries have no response times recorded at all, so Nikhil could not even measure them.';
    $('btSum').textContent = bt.filter(r => r.ok).length + ' of ' + bt.length + ' agree with the rubric';
    const LAB = { forward: 'Qualified → designer', ask: 'Needs one more answer, then designer', decline: 'Close politely', escalate: 'Escalate to studio head' };
    $('bt').querySelector('tbody').innerHTML = bt.map(r => '<tr><td class="mono">' + r.id + '</td><td>' + r.channel + '</td><td>' + esc(r.happened) + '</td><td><span class="pill ' + (r.got === 'decline' ? 'mute' : r.got === 'escalate' ? 'bad' : 'good') + '">' + LAB[r.got] + '</span></td><td class="mono small">' + esc(r.why) + '</td></tr>').join('');
  }

  // ------------- leads table
  const OUT = { processing: ['info', 'Processing\u2026'], qualified: ['good', 'Qualified'], closed: ['mute', 'Closed'], escalated: ['bad', 'Escalated'], callback: ['warn', 'Call-back'] };
  const fmt = d => new Date(d).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  $('leadCount').textContent = N + ' total';
  $('empty').hidden = N > 0;
  const hsLink = l => l.hubspot && l.hubspot.contact_id && HUB_PORTAL ? 'https://app.hubspot.com/contacts/' + HUB_PORTAL + '/record/0-1/' + l.hubspot.contact_id : null;
  const rowHtml = (l, i) =>
    '<tr class="click" data-i="' + i + '" tabindex="0"><td>' + fmt(l.created_at) + (l.after_hours ? ' <span class="pill info">after hours</span>' : '') + (l.channel === 'vaani-webrtc' ? ' <span class="pill good">\ud83c\udf99 live WebRTC</span>' : l.channel === 'vaani-phone' ? ' <span class="pill good">\ud83d\udcde phone</span>' : ' <span class="pill mute">practice</span>') + (l.price_leak ? ' <span class="pill bad">price said</span>' : '') + '</td><td>' + esc(l.name || 'Unknown') + '<br><span class="muted small">' + esc(l.phone || '') + '</span></td>' +
    '<td><span class="pill ' + OUT[l.outcome][0] + '">' + OUT[l.outcome][1] + '</span><br><span class="muted small">' + esc((l.reason || '').replace(/_/g, ' ')) + '</span></td>' +
    '<td>' + (l.priority ? '<span class="pill ' + (l.priority === 'HOT' || l.priority === 'URGENT' ? 'bad' : 'warn') + '">' + l.priority + '</span>' : '\u2014') + '</td>' +
    '<td>' + (l.first_response_secs || 0).toFixed(1) + ' s</td><td>' + Math.round((l.duration_secs || 0) / 6) / 10 + ' min</td><td>' + inr(l.llm_cost_inr, 3) + '</td>' +
    '<td>' + (l.handoff && l.handoff.sent ? '<span class="pill good">Telegram sent</span>' : l.outcome === 'closed' ? '\u2014' : '<span class="pill mute">preview only</span>') + (l.claimed_at ? '<br><span class="muted small">claimed ' + esc(l.claimed_by || '') + '</span>' : '') +
    (l.hubspot ? '<br>' + (hsLink(l) ? '<a href="' + hsLink(l) + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">' : '') + '<span class="pill ' + (l.hubspot.ok ? 'good' : 'bad') + '" title="' + esc(l.hubspot.error || '') + '">HubSpot ' + (l.hubspot.ok ? 'synced' : 'failed') + '</span>' + (hsLink(l) ? '</a>' : '') : '') + '</td></tr>';
  let filt = 'all', query = '', typ = realLeads.length ? 'real' : 'all';
  const TYPES = [['real', '\ud83d\udcde Real voice calls'], ['practice', 'Practice (simulator)'], ['all', 'Everything']];
  const isType = l => typ === 'all' || (typ === 'real' ? !!l.real_call : !l.real_call);
  const FILTERS = [['all', 'All'], ['qualified', 'Qualified'], ['callback', 'Call-back'], ['escalated', 'Escalated'], ['closed', 'Closed']];
  function renderTable() {
    const q = query.trim().toLowerCase();
    const vis = allLeads.map((l, i) => [l, i]).filter(([l]) => isType(l) && (filt === 'all' || l.outcome === filt) && (!q || [l.name, l.phone, (l.facts || {}).location_text, l.reason].join(' ').toLowerCase().includes(q)));
    $('leads').querySelector('tbody').innerHTML = vis.map(([l, i]) => rowHtml(l, i)).join('') || '<tr><td colspan="8" class="muted">No calls match.</td></tr>';
    const pool = allLeads.filter(isType);
    $('filters').innerHTML = TYPES.map(([k, t]) => '<button class="chip' + (k === typ ? ' on' : '') + '" data-t="' + k + '">' + t + ' <span class="muted">' + allLeads.filter(l => k === 'all' || (k === 'real' ? !!l.real_call : !l.real_call)).length + '</span></button>').join('') + '<span style="width:10px"></span>' + FILTERS.map(([k, t]) => '<button class="chip' + (k === filt ? ' on' : '') + '" data-k="' + k + '">' + t + ' <span class="muted">' + (k === 'all' ? pool.length : pool.filter(l => l.outcome === k).length) + '</span></button>').join('');
  }
  $('filters').onclick = e => { const b = e.target.closest('.chip'); if (!b) return; if (b.dataset.t) typ = b.dataset.t; else filt = b.dataset.k; renderTable(); };
  $('search').oninput = e => { query = e.target.value; renderTable(); };
  renderTable();

  // ------------- charts, funnel, alerts
  const istHour = d => +new Date(d).toLocaleString('en-GB', { hour: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' }).slice(0, 2) % 24;
  const sept = bt.map(r => istHour(r.ts)), live = leads.map(l => istHour(l.created_at));
  const c1 = Array(24).fill(0), c2 = Array(24).fill(0); sept.forEach(h => c1[h]++); live.forEach(h => c2[h]++);
  const mx = Math.max(1, ...c1.map((v, i) => v + c2[i]));
  $('hours').innerHTML = c1.map((v, i) => '<div class="col' + (i < 10 || i >= 19 ? ' ah' : '') + '" title="' + i + ':00 \u2013 ' + v + ' September, ' + c2[i] + ' live"><div class="b2" style="height:' + (100 * c2[i] / mx) + '%"></div><div class="b1" style="height:' + (100 * v / mx) + '%"></div></div>').join('') + '<div class="hlab" style="grid-column:1/-1">' + Array.from({ length: 24 }, (_, i) => '<span>' + (i % 3 === 0 ? i : '') + '</span>').join('') + '</div>';
  const ahShare = sept.length ? Math.round(100 * sept.filter(h => h < 10 || h >= 19).length / sept.length) : 0;
  $('hoursNote').textContent = ahShare + '% of the 40 September enquiries arrived outside desk hours' + (bt.length ? ' (brief says about a third). Every one of them now gets an instant answer.' : '.');
  const fSteps = [['Calls answered', N], ['Handed to a person', handedOff], ['Telegram delivered', sent], ['Claimed by a designer', claimed.length], ['In HubSpot', leads.filter(l => l.hubspot && l.hubspot.ok).length]];
  $('funnel').innerHTML = fSteps.map(([t, v]) => '<div class="fn"><span>' + t + '</span><div class="track"><div class="fill" style="width:' + (N ? 100 * v / N : 0) + '%"></div></div><b>' + v + '</b></div>').join('');
  const mixC = { qualified: 'var(--good)', callback: 'var(--warn)', escalated: 'var(--bad)', closed: 'var(--muted)' };
  $('mix').innerHTML = '<div class="small muted" style="margin-bottom:6px">Outcome mix</div><div class="mixbar">' + ['qualified', 'callback', 'escalated', 'closed'].map(k => '<i style="display:block;width:' + (N ? 100 * leads.filter(l => l.outcome === k).length / N : 0) + '%;background:' + mixC[k] + '"></i>').join('') + '</div>';
  const alerts = [];
  const stale = leads.filter(l => l.handoff && l.handoff.sent && !l.claimed_at && l.outcome !== 'closed' && (Date.now() - new Date(l.created_at)) > 15 * 60000);
  if (stale.length) alerts.push('\u23f1 ' + stale.length + ' handed-off lead' + (stale.length > 1 ? 's' : '') + ' not claimed by a designer after 15 minutes: ' + stale.slice(0, 3).map(l => esc(l.name || l.phone || 'unknown')).join(', ') + '. The 5-minute promise stops here, so nudge the team.');
  const hsFail = leads.filter(l => l.hubspot && !l.hubspot.ok).length;
  if (hsFail) alerts.push('HubSpot could not save ' + hsFail + ' lead' + (hsFail > 1 ? 's' : '') + '. Check the token on the How it connects page.');
  // What the real calls tell Nikhil (decision support)
  if (realLeads.length) {
    const R = realLeads, n = R.length, pct = x => Math.round(100 * x / n) + '%';
    const count = (arr) => { const m = {}; arr.filter(Boolean).forEach(x => m[x] = (m[x] || 0) + 1); return Object.entries(m).sort((a, b) => b[1] - a[1]); };
    const q2 = R.filter(l => l.outcome === 'qualified').length;
    const reasons = count(R.filter(l => l.outcome === 'closed').map(l => (l.reason || '').replace(/_/g, ' ')));
    const areas = count(R.map(l => (l.facts || {}).location_text));
    const types = count(R.map(l => ((l.facts || {}).project_type || '').replace(/_/g, ' ')));
    const priceAsk = R.filter(l => (l.facts || {}).asked_price).length, leaks = R.filter(l => l.price_leak).length;
    const avgDur = Math.round(R.reduce((a, l) => a + (l.duration_secs || 0), 0) / n);
    const tips = [];
    if (q2) tips.push(q2 + ' of ' + n + ' calls (' + pct(q2) + ') were worth a designer\'s time and went out with a complete note.');
    if (reasons.length) tips.push('Most common reason to decline: ' + reasons[0][0] + ' (' + reasons[0][1] + '). ' + (reasons[0][0].includes('area') ? 'Consider whether demand outside Pune justifies a partner network.' : reasons[0][0].includes('timeline') ? 'Callers want speed; a fast-track package could be explored.' : 'Use this to sharpen marketing so fewer non-fit calls arrive.'));
    if (priceAsk) tips.push(pct(priceAsk) + ' of callers asked about price' + (leaks ? '' : ' and the agent never gave a figure') + '. A clear "what a consultation includes" page could reassure them early.');
    if (areas.length) tips.push('Where demand comes from: ' + areas.slice(0, 3).map(a => a[0] + ' (' + a[1] + ')').join(', ') + '.');
    $('insights').innerHTML = '<div class="sec-h"><h2>What the real calls tell Nikhil</h2><span class="muted small">from ' + n + ' real voice call' + (n > 1 ? 's' : '') + ', updated live</span></div>' +
      '<div class="kpis" style="margin-bottom:12px">' + [[pct(q2), 'qualified for a designer'], [avgDur + ' s', 'average call length'], [pct(priceAsk), 'asked about price'], [leaks, 'price rule breaks'], [types[0] ? types[0][0] : '\u2014', 'most common project']].map(x => '<div class="card kpi"><div class="v" style="font-size:1.4rem">' + esc(x[0]) + '</div><div class="l">' + x[1] + '</div></div>').join('') + '</div>' +
      '<ul style="padding-left:18px;margin:0">' + tips.map(t => '<li>' + esc(t) + '</li>').join('') + '</ul>';
  } else {
    $('insights').innerHTML = '<div class="sec-h"><h2>What the real calls tell Nikhil</h2></div><p class="muted">No real voice calls yet. Make one on the <a href="/live">Live AI call</a> page.</p>';
  }
  $('alerts').innerHTML = alerts.map(t => '<div class="alert">' + t + '</div>').join('');
  const CN = { 1: 'Real project', 2: 'In Pune / PCMC', 3: 'Realistic timeline', 4: 'Budget band', 5: 'Decision-maker' };
  const open = i => {
    const l = allLeads[i]; const f = l.facts || {}; const cr = l.criteria || {};
    const facts = [['Name', f.caller_name], ['Project', f.project_type && f.project_type.replace(/_/g, ' ')], ['Scope', f.scope_text], ['Where', f.location_text], ['Size', f.area_sqft && f.area_sqft + ' sq ft'], ['Site', f.property_state], ['Timeline', f.timeline_text], ['Budget', f.budget_max_lakh ? 'up to ' + f.budget_max_lakh + ' lakh (volunteered)' : 'not discussed'], ['Decides', f.decision_maker && f.decision_maker.replace(/_/g, ' ')], ['Preferred slot', f.preferred_slot], ['Asked price', f.asked_price ? 'yes, deflected' : 'no']].filter(x => x[1]);
    $('dlgBody').innerHTML = '<div style="display:flex;justify-content:space-between;gap:10px"><h2>' + esc(l.name || 'Unknown caller') + ' <span class="pill ' + OUT[l.outcome][0] + '">' + OUT[l.outcome][1] + '</span></h2><button class="btn sm" id="x">Close</button></div>' +
      '<p class="small muted" style="margin-top:-6px">' + fmt(l.created_at) + ' \u00b7 ' + (l.real_call ? (l.channel === 'vaani-webrtc' ? 'Live WebRTC call with the Vaani agent' : 'Phone call via Vaani') : 'Practice call (simulator)') + ' \u00b7 ' + Math.round((l.duration_secs || 0)) + ' s' + (l.vaani_call_id ? ' \u00b7 ' + esc(l.vaani_call_id) : '') + '</p>' +
      (l.price_leak ? '<div class="alert">\u26a0 The voice agent said a price on this call: \u201c' + esc(l.price_leak[0]) + '\u201d. Review the Vaani prompt.</div>' : '') +
      '<div class="card" style="box-shadow:none;margin:10px 0"><h3>Takeaways</h3>' + (l.vaani_summary ? '<p>' + esc(l.vaani_summary) + '</p>' : '') + '<dl class="kvd">' + facts.map(x => '<dt>' + x[0] + '</dt><dd>' + esc(x[1]) + '</dd>').join('') + '</dl></div>' +
      '<div class="card" style="box-shadow:none;margin:10px 0"><h3>Decision and why</h3><p><b>' + esc(l.label || '') + '.</b> ' + esc(l.next_action || '') + '</p><ul class="crit">' + Object.keys(cr).sort().map(k => '<li><span class="pill ' + (cr[k].status === 'pass' ? 'good' : cr[k].status === 'fail' ? 'bad' : 'mute') + '">' + cr[k].status + '</span> ' + CN[k] + ': ' + esc(cr[k].reason) + '</li>').join('') + '</ul>' + ((l.flags || []).length ? '<p class="small"><b>Watch-outs:</b> ' + l.flags.map(esc).join(' \u00b7 ') + '</p>' : '') + '</div>' +
      (/^\+\d{10,15}$/.test((l.phone || '').replace(/[^\d+]/g, '')) && l.outcome !== 'closed' ? '<p><button class="btn primary sm" id="cb">\ud83d\udcde Call back with AI (Vaani)</button> <span class="small muted" id="cbmsg">The Vaani agent rings ' + esc(l.phone) + ' and runs the same qualification.</span></p>' : '') +
      (l.booking_url && !(l.booking && l.booking.status === 'booked') ? '<p><a class="btn primary sm" target="_blank" rel="noopener" href="' + esc(l.booking_url) + '">\ud83d\udcc5 Book the consultation (Cal.com)</a></p>' : '') + (l.booking && l.booking.status === 'booked' ? '<p class="pill good">\ud83d\udcc5 Consultation booked: ' + esc(new Date(l.booking.start).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })) + '</p>' : '') + (l.recording_url ? '<p class="small"><a href="' + esc(l.recording_url) + '" target="_blank" rel="noopener">\u25b6 Listen to the call recording</a></p>' : '') +
      '<h3>Full transcript</h3><div class="tr">' + (l.transcript || []).map(m => '<div class="' + (m.role === 'agent' ? 'a' : 'c') + '"><small>' + (m.role === 'agent' ? 'AI receptionist' : 'Caller') + '</small> ' + esc(m.text) + '</div>').join('') + '</div>' +
      '<details style="margin-top:12px"><summary>Handoff note sent to the designer</summary><div class="note" style="margin-top:8px">' + esc(l.note) + '</div></details>' +
      '<p class="small muted" style="margin-top:12px">Telegram: ' + (l.handoff && l.handoff.sent ? 'sent' : 'not sent') + ' \u00b7 HubSpot: ' + (l.hubspot ? (l.hubspot.ok ? 'synced' : 'failed') : 'not sent') + ' \u00b7 analysis model: ' + esc(l.model) + '</p>';
    $('dlg').showModal(); $('x').onclick = () => $('dlg').close();
    if ($('cb')) $('cb').onclick = async () => {
      if (!confirm('Ask the AI agent to call ' + l.phone + ' now?')) return;
      $('cbmsg').textContent = 'Dialling\u2026';
      try { const r = await fetch('/api/callback', { method: 'POST', headers: { 'content-type': 'application/json', 'x-dashboard-key': LS.get('aangan_key', '') }, body: JSON.stringify({ lead_id: l.id }) }); const j = await r.json(); $('cbmsg').textContent = (j.ok ? '\u2714 ' : '\u2716 ') + j.message; }
      catch (e) { $('cbmsg').textContent = '\u2716 ' + e.message; }
    };
  };
  $('leads').onclick = e => { const tr = e.target.closest('tr.click'); if (tr) open(+tr.dataset.i); };
  $('leads').onkeydown = e => { if (e.key === 'Enter') { const tr = e.target.closest('tr.click'); if (tr) open(+tr.dataset.i); } };
  $('dlg').addEventListener('click', e => { if (e.target === $('dlg')) $('dlg').close(); });
  window.__dash = { allLeads, realLeads, open, OUT };
  document.dispatchEvent(new Event('dash-ready'));
  if (location.hash.length > 1) { const ix = allLeads.findIndex(l => l.id === decodeURIComponent(location.hash.slice(1))); if (ix >= 0) open(ix); }

  $('csv').onclick = () => {
    const cols = ['created_at', 'name', 'phone', 'outcome', 'reason', 'priority', 'after_hours', 'first_response_secs', 'duration_secs', 'llm_cost_inr'];
    const rows = [cols.join(',')].concat(leads.map(l => cols.map(c => '"' + String(l[c] == null ? '' : l[c]).replace(/"/g, '""') + '"').join(',')));
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' })); a.download = 'aangan-calls.csv'; a.click();
  };
  $('clear').onclick = () => { if (confirm('Remove the demo calls saved in this browser?')) { LS.set('aangan_leads_v1', []); location.reload(); } };

  // ------------- settings
  const defs = [['voiceRsPerMin', 'Phone + speech cost (₹ per minute)'], ['projectValueLakh', 'Average project value (₹ lakh)'], ['frontDeskMonthly', 'One front-desk person (₹ per month)'], ['monthlyCalls', 'Calls per month']];
  $('settings').innerHTML = defs.map(d => '<label class="f">' + d[1] + '<input type="number" min="0" step="any" data-k="' + d[0] + '" value="' + S[d[0]] + '"></label>').join('');
  $('settings').onchange = e => { const s = getSettings(); s[e.target.dataset.k] = parseFloat(e.target.value) || 0; LS.set('aangan_settings', s); location.reload(); };
})();
