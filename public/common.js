// Shared helpers: theme-safe storage, settings, ledger, formatting.
const LS = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};
// magic link: any page opened as  /page#key=XXXX  saves the access key once and cleans the address bar
(function () { try { const h = new URLSearchParams(location.hash.slice(1)); const k = h.get('key'); if (k) { localStorage.setItem('aangan_key', JSON.stringify(k)); h.delete('key'); const rest = h.toString(); history.replaceState(null, '', location.pathname + location.search + (rest ? '#' + rest : '')); } } catch (e) {} })();
const SETTINGS_DEFAULT = {
  voiceRsPerMin: 5.6,       // Vaani's quoted running cost for this agent (Rs per minute, estimate shown in the Vaani dashboard)
  projectValueLakh: 11,     // midpoint of the Rs 8-14 lakh average project value in the brief
  frontDeskMonthly: 30000,  // ASSUMPTION: per-person monthly cost, only used for the comparison line
  monthlyCalls: 200,
};
const getSettings = () => Object.assign({}, SETTINGS_DEFAULT, LS.get('aangan_settings', {}));
const getLocalLeads = () => LS.get('aangan_leads_v1', []);
function saveLocalLead(l) { const a = getLocalLeads(); a.unshift(l); LS.set('aangan_leads_v1', a.slice(0, 500)); }
const inr = (n, d = 2) => '₹' + Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d });
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
async function api(path, body) {
  const key = LS.get('aangan_key', '');
  const r = await fetch(path, body === undefined ? { headers: key ? { 'x-dashboard-key': key } : {} } : { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
  return j;
}
