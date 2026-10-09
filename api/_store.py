"""Lead storage on Neon Postgres, using Neon's SQL-over-HTTP endpoint (no database driver needed).
Active when DATABASE_URL is set; otherwise the browser keeps leads in localStorage (demo mode)."""
import json
import os
import urllib.request
import urllib.error
from urllib.parse import urlparse

_ready = {"ok": False}

SCHEMA = """create table if not exists leads (
  id text primary key,
  created_at timestamptz not null default now(),
  data jsonb not null
)"""


def configured():
    return bool(os.environ.get("DATABASE_URL"))


def _sql(query, params=()):
    cs = os.environ["DATABASE_URL"]
    host = urlparse(cs).hostname
    req = urllib.request.Request(
        "https://%s/sql" % host,
        data=json.dumps({"query": query, "params": list(params)}).encode(),
        headers={"Neon-Connection-String": cs, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError("Neon %s: %s" % (e.code, e.read().decode()[:200]))


def _ensure():
    if not _ready["ok"]:
        _sql(SCHEMA)
        _sql("create table if not exists settings (key text primary key, value text not null)")
        _ready["ok"] = True


def _data(row):
    d = row["data"]
    return json.loads(d) if isinstance(d, str) else d


def save(lead):
    _ensure()
    _sql("insert into leads (id, created_at, data) values ($1, $2::timestamptz, $3::jsonb) "
         "on conflict (id) do update set data = excluded.data", [lead["id"], lead["created_at"], json.dumps(lead)])


def list_leads(limit=500):
    _ensure()
    return [_data(r) for r in _sql("select data from leads order by created_at desc limit %d" % int(limit)).get("rows", [])]


def get(lead_id):
    _ensure()
    rows = _sql("select data from leads where id = $1", [lead_id]).get("rows", [])
    return _data(rows[0]) if rows else None


def update(lead_id, patch):
    lead = get(lead_id)
    if not lead:
        return None
    lead.update(patch)
    save(lead)
    return lead


def get_setting(key):
    if not configured():
        return None
    _ensure()
    rows = _sql("select value from settings where key = $1", [key]).get("rows", [])
    return rows[0]["value"] if rows else None


def set_setting(key, value):
    _ensure()
    _sql("insert into settings (key, value) values ($1, $2) on conflict (key) do update set value = excluded.value", [key, str(value)])
