"""Signed personal LINE commands and expiring private notification settings."""
import base64
import hashlib
import hmac
import json
import time
import secrets
from html import escape
from aiohttp import web
from .engine import NOTIFICATION_TYPES
from .status import status_text
from receiver.logging import event as log_event


def application(engine, secret, recipient, settings_path="/settings"):
    engine.db.execute("CREATE TABLE IF NOT EXISTS app_line_events(id TEXT PRIMARY KEY, received REAL NOT NULL)")
    engine.db.commit()
    app = web.Application(client_max_size=65536)

    def settings_token():
        value = str(int(time.time()) + 3600) + ":" + secrets.token_hex(16)
        return value + ":" + hmac.new(secret.encode(), ("settings:" + settings_path + ":" + value).encode(), hashlib.sha256).hexdigest()

    def valid_token(token):
        try:
            expiry, nonce, signature = token.split(":")
            expected = hmac.new(secret.encode(), ("settings:" + settings_path + ":" + expiry + ":" + nonce).encode(), hashlib.sha256).hexdigest()
            return time.time() < int(expiry) <= time.time() + 3600 and hmac.compare_digest(signature, expected)
        except (ValueError, AttributeError):
            return False

    async def settings(request):
        token = request.query.get("token") or request.cookies.get("mcv_settings", "")
        if not valid_token(token):
            raise web.HTTPForbidden(text="Send settings to your LINE bot for a fresh private link.")
        headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                   "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
                   "X-Content-Type-Options": "nosniff"}
        if request.method == "GET" and "token" in request.query:
            response = web.HTTPSeeOther(settings_path, headers=headers)
            response.set_cookie("mcv_settings", token, httponly=True, secure=request.scheme == "https" or request.host.endswith(".trycloudflare.com"), samesite="Strict", max_age=3600, path=settings_path)
            return response
        saved = False
        if request.method == "POST":
            form = await request.post()
            if not hmac.compare_digest(str(form.get("csrf", "")), token):
                raise web.HTTPForbidden()
            if any(k not in NOTIFICATION_TYPES and k != "csrf" for k in form):
                raise web.HTTPBadRequest()
            engine.save_preferences({key: key in form for key in NOTIFICATION_TYPES})
            saved = True
        preferences = engine.preferences()
        controls = "".join('<label><input type="checkbox" name="' + key + '"' + (' checked' if preferences[key] else '') + '> ' + escape(label) + '</label>' for key, label in NOTIFICATION_TYPES.items())
        html = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>mCV notifications</title><style>body{font:18px system-ui;max-width:620px;margin:3rem auto;padding:1rem;background:#faf7f7;color:#292020}label{display:block;padding:1rem;background:white;margin:.5rem 0;border-radius:8px}button{background:#4d0000;color:white;border:0;padding:1rem 2rem;border-radius:8px}input{margin-right:.6rem}</style><h1>Notification settings</h1><p>Select the automatic LINE notifications you want. Homework and status commands always work. Homework reads saved assignments without refreshing CourseVille.</p><p>Push categories use exact title suffixes first, then metadata or CourseVille links. Assignment, material, score and announcement suffixes are verified in real notifications. Unrecognized or conflicting types appear under Other.</p>' + ('<p role="status">Settings saved.</p>' if saved else '') + '<form method="post" action="' + escape(settings_path, quote=True) + '"><input type="hidden" name="csrf" value="' + escape(token, quote=True) + '">' + controls + '<button>Save settings</button></form><p>Changes apply to pending and future notifications. Disabled alerts are skipped, not replayed later. This private link expires after one hour.</p></html>'
        return web.Response(text=html, content_type="text/html", headers=headers)

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
        log_event("webhook.received", count=len(events))
        now = time.time()
        with engine.db:
            for event in events:
                if event.get("source", {}).get("userId") != recipient:
                    log_event("webhook.recipient_mismatch")
                    continue
                event_id = event.get("webhookEventId")
                if not isinstance(event_id, str):
                    continue
                inserted = engine.db.execute("INSERT OR IGNORE INTO app_line_events VALUES(?,?)", (event_id, now)).rowcount
                if not inserted or event.get("type") != "message" or event.get("message", {}).get("type") != "text":
                    continue
                command = event["message"].get("text", "").strip().lower()
                if command == "homework":
                    engine.queue_homework(event_id, now)
                    continue
                if command == "settings":
                    text = "Private notification settings (expires in 1 hour): " + str(request.url.origin().with_scheme("https")) + settings_path + "?token=" + settings_token()
                elif command == "status":
                    text = status_text(engine, now)
                else:
                    text = "\n".join([
                        "mCV NOTIFIER",
                        "Choose a command:",
                        "",
                        "homework",
                        "Assignments due today through +7 days.",
                        "Uses saved data; no refresh.",
                        "",
                        "status",
                        "Latest update, received pushes and delivery queue.",
                        "",
                        "settings",
                        "Choose which notifications to receive.",
                        "",
                        "All dates and times use Bangkok (UTC+7).",
                        "Contact dev for account setup.",
                    ])
                engine._queue("line:" + event_id, "command", [], now, expires=now+300, text=text)
        return web.Response(text="OK")

    app.router.add_get(settings_path, settings)
    app.router.add_post(settings_path, settings)
    app.router.add_get("/healthz", health)
    app.router.add_post("/callback", callback)
    return app
