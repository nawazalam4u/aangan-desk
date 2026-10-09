"""POST /api/telegram - Telegram webhook. A designer taps 'I'll take it' -> lead is claimed, message updated."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler
from datetime import datetime
import os
from _http import read_json, send
import _core as c
import _store


def tg(method, payload):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    return c._post_json("https://api.telegram.org/bot%s/%s" % (tok, method), payload, {}, 10)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        if secret and self.headers.get("x-telegram-bot-api-secret-token") != secret:
            return send(self, {"ok": False}, 401)
        upd = read_json(self)
        cb = upd.get("callback_query")
        msg = upd.get("message") or {}
        try:
            text = (msg.get("text") or "").strip()
            if text.startswith("/register") or text.startswith("/start"):
                chat_id = msg["chat"]["id"]
                parts = text.split()
                want = os.environ.get("DASHBOARD_KEY")
                if parts[0].startswith("/register") and want and len(parts) > 1 and parts[1] == want and _store.configured():
                    _store.set_setting("telegram_chat", chat_id)
                    tg("sendMessage", {"chat_id": chat_id, "text": "\u2705 Registered. Qualified enquiries from Aangan Desk will be posted here."})
                else:
                    tg("sendMessage", {"chat_id": chat_id, "text": "To make this chat receive designer handoffs, send:\n/register <dashboard key>"})
        except Exception:
            pass
        try:
            if cb and str(cb.get("data", "")).startswith("claim:"):
                lead_id = cb["data"].split(":", 1)[1]
                who = (cb.get("from", {}).get("first_name") or "A designer")
                when = datetime.now(c.IST)
                if _store.configured():
                    _store.update(lead_id, {"claimed_at": when.isoformat(), "claimed_by": who})
                tg("answerCallbackQuery", {"callback_query_id": cb["id"], "text": "Yours. Good luck!"})
                m = cb.get("message", {})
                tg("editMessageText", {"chat_id": m["chat"]["id"], "message_id": m["message_id"],
                                        "text": m.get("text", "") + "\n\n✅ Claimed by %s at %s" % (who, when.strftime("%I:%M %p"))})
        except Exception:
            pass
        send(self, {"ok": True})

    def log_message(self, *a):
        pass
