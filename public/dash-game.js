// Gamified layer: Studio Pulse score, level/XP, achievements and call cards. Everything is computed from REAL calls.
document.addEventListener('dash-ready', function () {
  const { allLeads, realLeads, open } = window.__dash;
  const R = realLeads, n = R.length, $ = id => document.getElementById(id);
  const cnt = f => R.filter(f).length;
  const q = cnt(l => l.outcome === 'qualified'), esc2 = cnt(l => l.outcome === 'escalated'), booked = cnt(l => l.booking && l.booking.status === 'booked');
  const leaks = cnt(l => l.price_leak), after = cnt(l => l.after_hours), hs = cnt(l => l.hubspot && l.hubspot.ok);
  const claimed = cnt(l => l.claimed_at), handed = cnt(l => l.outcome !== 'closed');
  const multi = cnt(l => /hindi|marathi/i.test((l.facts || {}).language || ''));
  const fast = R.map(l => l.first_response_secs || 1).sort((a, b) => a - b)[Math.floor(n / 2)] || 1;
  // Studio Pulse: 40 speed + 25 price discipline + 20 routed (handed off or politely closed with a reason) + 15 follow-through (claimed or booked)
  const pulse = n ? Math.round(40 * (R.filter(l => (l.first_response_secs || 1) <= 300).length / n) + 25 * (1 - leaks / n) + 20 * (R.filter(l => l.outcome !== 'closed' || l.reason).length / n) + 15 * Math.min(1, (claimed + booked) / Math.max(1, handed))) : 0;
  const xp = n * 10 + q * 25 + booked * 40 + esc2 * 15 + after * 10 + multi * 20;
  const lvl = Math.floor(Math.sqrt(xp / 50)) + 1, cur = 50 * Math.pow(lvl - 1, 2), next = 50 * Math.pow(lvl, 2);
  const titles = ['Rookie receptionist', 'Reliable responder', 'Lead whisperer', 'Pipeline pro', 'Studio legend'];
  const C = 2 * Math.PI * 62;
  $('hero').innerHTML = '<div class="ring" role="img" aria-label="Studio pulse ' + pulse + ' out of 100"><svg width="150" height="150"><circle cx="75" cy="75" r="62" fill="none" stroke="rgba(255,255,255,.15)" stroke-width="12"/><circle id="arc" cx="75" cy="75" r="62" fill="none" stroke="url(#g)" stroke-width="12" stroke-linecap="round" stroke-dasharray="' + C + '" stroke-dashoffset="' + C + '" style="transition:stroke-dashoffset 1.4s ease"/><defs><linearGradient id="g"><stop offset="0" stop-color="#f6c177"/><stop offset="1" stop-color="#e0764f"/></linearGradient></defs></svg><div class="val"><div><b class="count" data-to="' + pulse + '">0</b><br><span>Studio pulse</span></div></div></div>' +
    '<div><div class="lvl">⭐ Level ' + lvl + ' · ' + titles[Math.min(lvl - 1, titles.length - 1)] + '</div><h2>' + (n ? 'Every caller answered, every lead routed.' : 'Ready for the first real call') + '</h2><p>' + (n ? n + ' real voice calls · median answer ' + fast.toFixed(1) + ' s · ' + (leaks ? leaks + ' price slip' + (leaks > 1 ? 's' : '') : 'zero prices quoted') : 'Make a call on the Live AI call page to start scoring.') + '</p><div class="xpbar" title="' + xp + ' XP"><i id="xpb" style="width:0"></i></div><small style="opacity:.75">' + xp + ' XP · ' + Math.max(0, next - xp) + ' XP to level ' + (lvl + 1) + '</small></div>' +
    '<div class="mini"><div><b class="count" data-to="' + n + '">0</b><span>real calls</span></div><div><b class="count" data-to="' + q + '">0</b><span>qualified</span></div><div><b class="count" data-to="' + booked + '">0</b><span>consults booked</span></div><div><b class="count" data-to="' + hs + '">0</b><span>in HubSpot</span></div></div>';
  requestAnimationFrame(() => { $('arc').style.strokeDashoffset = C * (1 - pulse / 100); $('xpb').style.width = Math.min(100, 100 * (xp - cur) / Math.max(1, next - cur)) + '%'; });
  document.querySelectorAll('.count').forEach(el => { const to = +el.dataset.to, t0 = performance.now(); const step = t => { const k = Math.min(1, (t - t0) / 900); el.textContent = Math.round(to * k); if (k < 1) requestAnimationFrame(step); }; requestAnimationFrame(step); });
  const B = [
    ['📞', 'First voice call', 'A real caller spoke to the agent', n >= 1],
    ['🎯', 'Closer', 'First qualified lead sent to a designer', q >= 1],
    ['🛡️', 'Iron rule', '3+ calls and not one price quoted', n >= 3 && !leaks],
    ['🧘', 'Calm under fire', 'Handled an angry client by escalating', esc2 >= 1],
    ['📅', 'Booked!', 'First consultation booked on Cal.com', booked >= 1],
    ['🤝', 'CRM pro', '3 leads synced to HubSpot', hs >= 3],
    ['🌙', 'Night owl', 'Answered a call after 7pm', after >= 1],
    ['🗣️', 'Polyglot', 'Handled a Hindi or Marathi caller', multi >= 1],
    ['⚡', 'Speed demon', 'Median answer under 2 seconds', n >= 1 && fast < 2],
    ['🏆', 'Ten calls', '10 real calls handled', n >= 10]];
  $('badges').innerHTML = B.map(b => '<div class="badge ' + (b[3] ? 'on' : 'off') + '" title="' + b[2] + '"><span class="ic" aria-hidden="true">' + b[0] + '</span><b>' + b[1] + '</b><small>' + (b[3] ? 'Unlocked' : b[2]) + '</small></div>').join('');
  const OUTL = { qualified: 'Qualified', closed: 'Closed', escalated: 'Escalated', callback: 'Call-back' };
  const e = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const qb = (k, v) => v == null ? '' : '<div class="qbar"><span>' + k + '</span><i><b style="width:' + (v * 10) + '%"></b></i><span>' + v + '</span></div>';
  $('feed').innerHTML = R.slice(0, 9).map(l => { const qq = l.vaani_quality || {}; const nm = l.name || 'Caller'; return '<div class="ccard ' + l.outcome + '" tabindex="0" data-id="' + e(l.id) + '"><div class="top"><span class="av">' + e(nm[0].toUpperCase()) + '</span><div><b>' + e(nm) + '</b><br><span class="small muted">' + new Date(l.created_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) + ' · ' + Math.round(l.duration_secs || 0) + ' s</span></div><span class="pill ' + ({ qualified: 'good', closed: 'mute', escalated: 'bad', callback: 'warn' }[l.outcome]) + '" style="margin-left:auto">' + OUTL[l.outcome] + '</span></div><p>' + e(l.vaani_summary || l.next_action || '') + '</p>' + qb('Clarity', qq.clarity) + qb('Professional', qq.professionalism) + (l.booking && l.booking.status === 'booked' ? '<span class="pill good">📅 consult booked</span>' : '') + '</div>'; }).join('') || '<p class="muted">No real calls yet. <a href="/live">Make the first one</a>.</p>';
  $('feed').onclick = ev => { const c = ev.target.closest('.ccard'); if (c) open(allLeads.findIndex(x => x.id === c.dataset.id)); };
  $('feed').onkeydown = ev => { if (ev.key === 'Enter') { const c = ev.target.closest('.ccard'); if (c) open(allLeads.findIndex(x => x.id === c.dataset.id)); } };
});
