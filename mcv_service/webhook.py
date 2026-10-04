"""Only the signed personal LINE callback is exposed; no public admin API."""
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime
from aiohttp import web
from .engine import BANGKOK


def application(engine, secret, recipient):
    engine.db.execute("CREATE TABLE IF NOT EXISTS app_line_events(id TEXT PRIMARY KEY, received REAL NOT NULL)")
    engine.db.commit()
    app = web.Application(client_max_size=65536)

    async def health(request):
        return web.json_response({"ready": True})

    async def callback(request):
        body = await request.read()
        signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, request.headers.get("X-Line-Signature", "").encode()):
            raise web.HTTPBadRequest()
        try:
            payload = json.loads(body)
            events = payload["events"]
            if not isinstance(events, list) or any(not isinstance(e, dict) for e in events):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise web.HTTPBadRequest() from None
        now = time.time()
        with engine.db:
            for event in events:
                if event.get("source", {}).get("userId") != recipient:
                    continue
                event_id = event.get("webhookEventId")
                if not isinstance(event_id, str):
                    continue
                inserted = engine.db.execute("INSERT OR IGNORE INTO app_line_events VALUES(?,?)", (event_id, now)).rowcount
                if not inserted or event.get("type") != "message" or event.get("message", {}).get("type") != "text":
                    continue
                command = event["message"].get("text", "").strip().lower()
                if command == "status":
                    last = engine.store.get("last_refresh")
                    text = "mCV service is running. Last assignment refresh: " + (datetime.fromtimestamp(last, BANGKOK).strftime("%d %b %H:%M Bangkok") if last else "not yet")
                else:
                    text = "Personal mCV notifier. Send status for service status. Account setup is local; do not send passwords here."
                engine._queue("line:" + event_id, "command", [], now, expires=now+300, text=text)
        return web.Response(text="OK")

    app.router.add_get("/healthz", health)
    app.router.add_post("/callback", callback)
    return app
