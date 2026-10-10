// Live WebRTC call with the Vaani agent. Flow: /api/live -> LiveKit token -> join room with the mic -> agent talks.
(function () {
  const $ = id => document.getElementById(id);
  const LK = window.LivekitClient;
  let room = null, ws = null, timerId = null, started = 0, roomName = '';

  // URL fragment options (used for automated test calls): #key=...&autostart=1&hangup=90
  const frag = new URLSearchParams(location.hash.slice(1));
  if (frag.get('key')) { LS.set('aangan_key', frag.get('key')); history.replaceState(null, '', location.pathname); }
  const key = () => LS.get('aangan_key', '');
  const showKey = msg => { $('keyCard').hidden = false; $('keyMsg').textContent = msg || ''; };
  if (!key()) showKey();
  $('saveKey').onclick = () => { LS.set('aangan_key', $('key').value.trim()); $('keyCard').hidden = true; };

  function setState(t, sub, mode) { console.log('[live]', t, '|', sub || ''); $('status').textContent = t; if (sub != null) $('sub').textContent = sub; $('orb').className = 'orb ' + (mode || 'idle'); }
  function cap(role, text) {
    if (!text) return;
    const d = document.createElement('div'); d.className = 'cap ' + (role === 'agent' ? 'a' : 'u');
    console.log('[caption]', role, text);
    d.innerHTML = '<small>' + (role === 'agent' ? 'AI receptionist' : 'You') + '</small>' + esc(text);
    $('captions').appendChild(d); $('captions').scrollTop = $('captions').scrollHeight;
  }

  async function start() {
    if (!LK) return setState('Could not load the call library', 'Check your internet connection and reload.');
    if (!key()) return showKey('Enter the key to start a live call.');
    $('startBtn').disabled = true; setState('Connecting…', 'Asking Vaani for a secure call session', 'idle');
    let s;
    try {
      const r = await fetch('/api/live', { method: 'POST', headers: { 'content-type': 'application/json', 'x-dashboard-key': key() }, body: JSON.stringify({ mode: 'webrtc' }) });
      s = await r.json();
      if (r.status === 401) { $('startBtn').disabled = false; showKey('That key was not accepted.'); return setState('Ready'); }
      if (!s.ok) throw new Error(s.message);
    } catch (e) { $('startBtn').disabled = false; return setState('Could not start the call', e.message); }
    roomName = s.room_name; $('room').textContent = roomName;
    if (frag.get('debug')) LK.setLogLevel('debug');
    room = new LK.Room();
    room.on(LK.RoomEvent.TrackSubscribed, (track) => { if (track.kind === 'audio') { const el = track.attach(); el.autoplay = true; document.body.appendChild(el); } });
    room.on(LK.RoomEvent.ActiveSpeakersChanged, (sp) => {
      const agentTalking = sp.some(p => p.identity !== room.localParticipant.identity);
      const meTalking = sp.some(p => p.identity === room.localParticipant.identity);
      setState('Connected', agentTalking ? 'The receptionist is speaking…' : meTalking ? 'Listening to you…' : 'Your turn to speak', agentTalking || meTalking ? 'talk' : 'idle');
    });
    room.on(LK.RoomEvent.Disconnected, () => finish());
    try {
      await room.connect(s.server_url, s.token);
      await room.localParticipant.setMicrophoneEnabled(true);
    } catch (e) { $('startBtn').disabled = false; return setState('Microphone or connection problem', e.message); }
    started = Date.now(); timerId = setInterval(() => { const t = Math.floor((Date.now() - started) / 1000); $('timer').textContent = Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); }, 500);
    $('startBtn').hidden = true; $('endBtn').hidden = false; $('muteBtn').hidden = false; $('captions').innerHTML = '';
    setState('Connected', 'The receptionist will greet you in a moment', 'talk');
    openCaptions(s.live_captions_url);
    const h = +frag.get('hangup'); if (h) setTimeout(() => room && room.disconnect(), h * 1000);
  }

  function openCaptions(url) {
    if (!url) return;
    try {
      ws = new WebSocket(url);
      ws.onmessage = ev => {
        let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
        const items = Array.isArray(m) ? m : (m.data && Array.isArray(m.data) ? m.data : [m.data || m]);
        items.forEach(x => {
          if (!x || typeof x !== 'object') return;
          const text = x.text || x.transcript || x.message || x.content;
          const who = String(x.role || x.speaker || x.participant || x.sender || '').toLowerCase();
          if (text && (x.final !== false && x.is_final !== false)) cap(/agent|assistant|bot/.test(who) ? 'agent' : 'user', text);
        });
      };
    } catch (e) {}
  }

  let done = false;
  async function finish() {
    if (done) return; done = true;
    clearInterval(timerId); try { ws && ws.close(); } catch (e) {}
    $('endBtn').hidden = true; $('muteBtn').hidden = true;
    setState('Call ended', 'Vaani is writing the transcript. Our rules then decide what happens next.', 'idle');
    $('result').hidden = false; $('resTitle').textContent = 'Call result';
    $('resBody').innerHTML = 'Waiting for the transcript and decision (usually under a minute)&hellip;';
    const id = 'V-' + roomName.replace(/[^A-Za-z0-9-]/g, '');
    for (let i = 0; i < 40; i++) {
      await new Promise(r => setTimeout(r, 6000));
      try {
        const r = await fetch('/api/leads', { headers: { 'x-dashboard-key': key() } }); const j = await r.json();
        const l = (j.leads || []).find(x => x.id === id);
        if (l) return showResult(l);
      } catch (e) {}
    }
    $('resBody').textContent = 'Still processing at Vaani. It will appear on the dashboard as soon as it arrives.';
  }

  function showResult(l) {
    const T = { qualified: ['good', 'Qualified, sent to a designer'], closed: ['mute', 'Closed politely (not a fit)'], escalated: ['bad', 'Escalated to a senior person'], callback: ['warn', 'Call-back queued'] };
    const f = l.facts || {};
    $('resTitle').innerHTML = 'Call result <span class="pill ' + T[l.outcome][0] + '">' + T[l.outcome][1] + '</span>';
    $('resBody').innerHTML = '<dl class="k">' +
      '<dt>Takeaway</dt><dd>' + esc(l.vaani_summary || '') + '</dd>' +
      '<dt>Caller</dt><dd>' + esc([f.caller_name, f.project_type && f.project_type.replace(/_/g, ' '), f.location_text, f.area_sqft && f.area_sqft + ' sq ft'].filter(Boolean).join(' · ') || '—') + '</dd>' +
      '<dt>Next action</dt><dd>' + esc(l.next_action || '') + '</dd>' +
      '<dt>Telegram</dt><dd>' + (l.handoff && l.handoff.sent ? 'sent to the designers' : l.outcome === 'closed' ? 'not needed' : 'not sent') + '</dd>' +
      '<dt>HubSpot</dt><dd>' + (l.hubspot ? (l.hubspot.ok ? 'contact and deal created' : 'failed') : 'not sent (closed calls stay out of the CRM)') + '</dd>' +
      '<dt>Price said?</dt><dd>' + (l.price_leak ? '<b style="color:var(--bad)">Yes, flagged</b>' : 'No') + '</dd></dl>' +
      '<p style="margin-top:10px"><a class="btn sm" href="/dashboard#' + encodeURIComponent(l.id) + '">Open full transcript on the dashboard</a></p>';
  }

  $('startBtn').onclick = start;
  $('endBtn').onclick = () => room && room.disconnect();
  $('muteBtn').onclick = async () => { const on = room.localParticipant.isMicrophoneEnabled; await room.localParticipant.setMicrophoneEnabled(!on); $('muteBtn').textContent = on ? 'Unmute' : 'Mute'; $('muteBtn').setAttribute('aria-pressed', on); };
  $('dialBtn').onclick = async () => {
    if (!key()) return showKey('Enter the key to place a call.');
    $('dialMsg').textContent = 'Dialling…';
    try {
      const r = await fetch('/api/live', { method: 'POST', headers: { 'content-type': 'application/json', 'x-dashboard-key': key() }, body: JSON.stringify({ mode: 'phone', number: $('num').value, name: $('nm').value }) });
      const j = await r.json(); $('dialMsg').textContent = (j.ok ? '✔ ' : '✖ ') + j.message; $('dialMsg').style.color = j.ok ? 'var(--good)' : 'var(--bad)';
    } catch (e) { $('dialMsg').textContent = '✖ ' + e.message; }
  };
  window.addEventListener('beforeunload', () => { try { room && room.disconnect(); } catch (e) {} });
  if (frag.get('autostart')) setTimeout(start, 800);
})();
