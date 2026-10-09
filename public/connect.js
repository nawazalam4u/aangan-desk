(async function () {
  const $ = id => document.getElementById(id);
  $('key').value = LS.get('aangan_key', '');
  $('saveKey').onclick = () => { LS.set('aangan_key', $('key').value.trim()); $('keyMsg').textContent = 'Saved.'; };
  try {
    const st = await (await fetch('/api/integrations')).json();
    document.querySelectorAll('.node[data-k]').forEach(n => {
      const s = st[n.dataset.k]; if (!s) return;
      n.querySelector('.led').className = 'led ' + (s.on ? 'on' : 'off');
      n.querySelector('.lt').textContent = (s.on ? 'Connected · ' : 'Not connected · ') + s.detail;
    });
  } catch (e) {}
  document.querySelectorAll('button[data-t]').forEach(b => b.onclick = async () => {
    const out = b.parentElement.querySelector('.res'); out.textContent = 'Testing…'; out.style.color = '';
    try {
      const r = await fetch('/api/integrations', { method: 'POST', headers: { 'content-type': 'application/json', 'x-dashboard-key': LS.get('aangan_key', '') }, body: JSON.stringify({ check: b.dataset.t }) });
      const j = await r.json(); out.textContent = (j.ok ? '✔ ' : '✖ ') + j.message; out.style.color = j.ok ? 'var(--good)' : 'var(--bad)';
      b.parentElement.querySelector('.led').className = 'led ' + (j.ok ? 'on' : 'bad');
    } catch (e) { out.textContent = '✖ ' + e.message; out.style.color = 'var(--bad)'; }
  });
})();
