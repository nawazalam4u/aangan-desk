import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def read_json(h):
    n = int(h.headers.get("content-length") or 0)
    raw = h.rfile.read(n) if n else b"{}"
    try:
        return json.loads(raw.decode() or "{}")
    except ValueError:
        return {}


def send(h, obj, status=200):
    b = json.dumps(obj).encode()
    h.send_response(status)
    h.send_header("content-type", "application/json")
    h.send_header("cache-control", "no-store")
    h.send_header("content-length", str(len(b)))
    h.end_headers()
    h.wfile.write(b)


def clamp_transcript(tr, max_msgs=60, max_chars=600):
    """Public endpoint: never let a caller push huge inputs into the AI or the database."""
    out = []
    for m in (tr or [])[-max_msgs:]:
        if isinstance(m, dict) and m.get("role") in ("agent", "caller"):
            out.append({"role": m["role"], "text": str(m.get("text", ""))[:max_chars]})
    return out
