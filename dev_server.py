"""Tiny local server so you can run the whole site on your laptop without Vercel:  python3 dev_server.py"""
import importlib
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "api"))
env = os.path.join(ROOT, ".env")
if os.path.exists(env):
    for line in open(env):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))
TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png"}


class H(BaseHTTPRequestHandler):
    def _api(self, verb):
        name = self.path.split("?")[0][5:].strip("/")
        try:
            mod = importlib.import_module(name)
            importlib.reload(mod)
            getattr(mod.handler, "do_" + verb)(self)
        except (ImportError, AttributeError):
            self.send_error(404)

    def do_POST(self):
        self._api("POST")

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        p = self.path.split("?")[0]
        p = "/index.html" if p == "/" else p
        if os.path.exists(os.path.join(ROOT, "public", p.lstrip("/") + ".html")):
            p += ".html"
        f = os.path.join(ROOT, "public", p.lstrip("/"))
        if not os.path.isfile(f):
            f = os.path.join(ROOT, p.lstrip("/")) if p.startswith("/data/") else f
        if not os.path.isfile(f):
            return self.send_error(404)
        b = open(f, "rb").read()
        self.send_response(200)
        self.send_header("content-type", TYPES.get(os.path.splitext(f)[1], "text/plain"))
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    print("Aangan Desk running on http://localhost:%d" % port)
    HTTPServer(("127.0.0.1", port), H).serve_forever()
