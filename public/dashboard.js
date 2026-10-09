(async function () {
  const $ = id => document.getElementById(id);
  const S = getSettings();
  const AVG_PHONE_MIN = 4.6; // mean of the 20 September call lengths in the transcripts
  const EST_LLM_PER_CALL = 0.4; // Rs, estimate before live data: ~10k input + ~1.5k output tokens on Gemini 3.1 Flash-Lite

  let leads = [], mode = 'local', bt = [], HUB_PORTAL = null;
  try { HUB_PORTAL = (await (await fetch('/api/integrations')).json()).hubspot.portal; } catch (e) {}
  let lockMsg = '';
  async function loadLeads() {
    const r = await fetch('/api/leads', { headers: { 'x-dashboard-key': LS.get('aangan_key', '') } });
    const j = await r.json().catch(() => ({})); return { status: r.status, j };
  }
  try {
    let { status, j } = await loadLeads();
    if (j.mode === 'locked' && status === 401) {
      const k = prompt('Dashboard key (set as DASHBOARD_KEY on Vercel):'); if (k) { LS.set('aangan_key', k); ({ status, j } = await loadLeads()); }
    }
    mode = j.mode || 'local'; leads = j.leads || []; if (j.mode === 'locked') lockMsg = j.error || 'Dashboard is locked.';
  } catch (e) {}
  if (mode === 'local') leads = getLocalLeads();
  if (mode === 'locked') { leads = []; }
  try { bt = await (await fetch('/data/backtest.json')).json(); } catch (e) {}

  const phRows = bt.filter(r => r.channel === 'phone');
  const qualRate = phRows.length ? phRows.filter(r => r.got === 'forward' || r.got === 'ask').length / phRows.length : 0.6; // share of September phone calls that reach a designer
  $('mode').className = 'banner' + (mode === 'shared' ? ' ok' : '');
  if (mode === 'locked') { $('mode').textContent = lockMsg + ' Reload to enter the key again.'; LS.set('aangan_key', ''); }
  if (mode !== 'locked') $('mode').textContent = mode === 'shared' ? 'Shared database connected: every call from every device appears here.' : 'Demo mode: showing calls made in this browser (plus the September baseline). Connect the shared database to see calls from all devices.';

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
  const voicePerCall = AVG_PHONE_MIN * S.voiceRsPerMin;
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
    k(esc_ + cb, 'Escalated / call-back queued', esc_ + ' escalated · ' + cb + ' dropped calls', 'warn') +
    k(claimMin == null ? '—' : claimMin.toFixed(1) + ' min', 'Designer claims a lead in', claimed.length ? claimed.length + ' claimed' : 'needs Telegram connected');

  // ------------- cost
  const llmPerCall = llmAvg == null ? EST_LLM_PER_CALL : llmAvg;
  const perCall = llmPerCall + voicePerCall;
  const monthly = perCall * S.monthlyCalls;
  $('costBasis').textContent = llmAvg == null ? 'AI cost is an estimate until a call runs on the live AI' : 'AI cost measured on ' + aiLeads.length + ' live-AI call' + (aiLeads.length > 1 ? 's' : '');
  const row = (a, b, cls) => '<span' + (cls ? ' class="' + cls + '"' : '') + '>' + a + '</span><span' + (cls ? ' class="' + cls + '"' : '') + '>' + b + '</span>';
  $('costKv').innerHTML =
    row('AI model (' + esc((leads.find(l => l.model && l.model !== 'demo-rules') || {}).model || 'Gemini 3.1 Flash-Lite') + ')<span class="meas">' + (llmAvg == null ? 'estimate' : 'measured') + '</span>', inr(llmPerCall, 2) + ' / call') +
    row('Phone + speech layer<span class="assume">assumption</span>', inr(voicePerCall, 0) + ' / call (' + AVG_PHONE_MIN + ' min)') +
    row('Hosting (Vercel free tier)', '₹0') +
    row('Cost per call', inr(perCall, 2), 'tot') +
    row('Cost per qualified lead', inr(perCall / qualRate, 0) + ' (at the September qualified rate)') +
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
  const OUT = { qualified: ['good', 'Qualified'], closed: ['mute', 'Closed'], escalated: ['bad', 'Escalated'], callback: ['warn', 'Call-back'] };
  const fmt = d => new Date(d).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  $('leadCount').textContent = N + ' total';
  $('empty').hidden = N > 0;
  const hsLink = l => l.hubspot && l.hubspot.contact_id && HUB_PORTAL ? 'https://app.hubspot.com/contacts/' + HUB_PORTAL + '/record/0-1/' + l.hubspot.contact_id : null;
  const rowHtml = (l, i) =>
    '<tr class="click" data-i="' + i + '" tabindex="0"><td>' + fmt(l.created_at) + (l.after_hours ? ' <span class="pill info">after hours</span>' : '') + '</td><td>' + esc(l.name || 'Unknown') + '<br><span class="muted small">' + esc(l.phone || '') + '</span></td>' +
    '<td><span class="pill ' + OUT[l.outcome][0] + '">' + OUT[l.outcome][1] + '</span><br><span class="muted small">' + esc((l.reason || '').replace(/_/g, ' ')) + '</span></td>' +
    '<td>' + (l.priority ? '<span class="pill ' + (l.priority === 'HOT' || l.priority === 'URGENT' ? 'bad' : 'warn') + '">' + l.priority + '</span>' : '\u2014') + '</td>' +
    '<td>' + (l.first_response_secs || 0).toFixed(1) + ' s</td><td>' + Math.round((l.duration_secs || 0) / 6) / 10 + ' min</td><td>' + inr(l.llm_cost_inr, 3) + '</td>' +
    '<td>' + (l.handoff && l.handoff.sent ? '<span class="pill good">Telegram sent</span>' : l.outcome === 'closed' ? '\u2014' : '<span class="pill mute">preview only</span>') + (l.claimed_at ? '<br><span class="muted small">claimed ' + esc(l.claimed_by || '') + '</span>' : '') +
    (l.hubspot ? '<br>' + (hsLink(l) ? '<a href="' + hsLink(l) + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">' : '') + '<span class="pill ' + (l.hubspot.ok ? 'good' : 'bad') + '" title="' + esc(l.hubspot.error || '') + '">HubSpot ' + (l.hubspot.ok ? 'synced' : 'failed') + '</span>' + (hsLink(l) ? '</a>' : '') : '') + '</td></tr>';
  let filt = 'all', query = '';
  const FILTERS = [['all', 'All'], ['qualified', 'Qualified'], ['callback', 'Call-back'], ['escalated', 'Escalated'], ['closed', 'Closed']];
  function renderTable() {
    const q = query.trim().toLowerCase();
    const vis = leads.map((l, i) => [l, i]).filter(([l]) => (filt === 'all' || l.outcome === filt) && (!q || [l.name, l.phone, (l.facts || {}).location_text, l.reason].join(' ').toLowerCase().includes(q)));
    $('leads').querySelector('tbody').innerHTML = vis.map(([l, i]) => rowHtml(l, i)).join('') || '<tr><td colspan="8" class="muted">No calls match.</td></tr>';
    $('filters').innerHTML = FILTERS.map(([k, t]) => '<button class="chip' + (k === filt ? ' on' : '') + '" data-k="' + k + '">' + t + ' <span class="muted">' + (k === 'all' ? N : leads.filter(l => l.outcome === k).length) + '</span></button>').join('');
  }
  $('filters').onclick = e => { const b = e.target.closest('.chip'); if (b) { filt = b.dataset.k; renderTable(); } };
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
  $('alerts').innerHTML = alerts.map(t => '<div class="alert">' + t + '</div>').join('');
  const open = i => {
    const l = leads[i];
    $('dlgBody').innerHTML = '<div style="display:flex;justify-content:space-between;gap:10px"><h2>' + esc(l.name || 'Unknown caller') + ' <span class="pill ' + OUT[l.outcome][0] + '">' + OUT[l.outcome][1] + '</span></h2><button class="btn sm" id="x">Close</button></div>' +
      '<h3>Handoff note</h3><div class="note">' + esc(l.note) + '</div><h3 style="margin-top:14px">Transcript</h3><div class="tr">' + (l.transcript || []).map(m => '<div class="' + (m.role === 'agent' ? 'a' : 'c') + '">' + esc(m.text) + '</div>').join('') + '</div>' +
      '<p class="small muted" style="margin-top:12px">Model: ' + esc(l.model) + ' · tokens in/out: ' + ((l.usage || {}).input || 0) + '/' + ((l.usage || {}).output || 0) + ' · price attempts blocked: ' + (l.price_blocked || 0) + '</p>';
    $('dlg').showModal(); $('x').onclick = () => $('dlg').close();
  };
  $('leads').onclick = e => { const tr = e.target.closest('tr.click'); if (tr) open(+tr.dataset.i); };
  $('leads').onkeydown = e => { if (e.key === 'Enter') { const tr = e.target.closest('tr.click'); if (tr) open(+tr.dataset.i); } };
  $('dlg').addEventListener('click', e => { if (e.target === $('dlg')) $('dlg').close(); });

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
