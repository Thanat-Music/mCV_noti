"""Personal runtime. Dry-run by default; --send explicitly enables LINE delivery."""
import argparse
import asyncio
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import signal
import sqlite3
import time

from receiver.autopush import Receiver, subscription
from receiver.courseville import legacy_account, login
from receiver.logging import configure, event
from receiver.store import Store, ReceiverLock
from .engine import Engine, BANGKOK
from .line import Line, DeliveryError


def credentials(args):
    # Explicit single-account selection, no credential data in process arguments.
    username, password = legacy_account(args.legacy_database, args.legacy_key, args.legacy_user)
    db = sqlite3.connect(Path(args.legacy_database).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        recipient = db.execute("SELECT Line_uid FROM user WHERE user_id=?", (args.legacy_user,)).fetchone()[0]
    finally:
        db.close()
    from dotenv import dotenv_values
    values = dotenv_values(args.line_env)
    return username, password, values.get("CHANNEL_ACCESS_TOKEN"), recipient, values.get("CHANNEL_SECRET")


async def daemon(args):
    os.umask(0o077)
    with ReceiverLock(args.database):
        store = Store(args.database)
        stop = asyncio.Event()
        receiver_task = None
        web_runner = None
        try:
            engine = Engine(store)
            receiver = Receiver(store)
            username, password, token, recipient, channel_secret = credentials(args)
            if args.send and (not token or not recipient):
                raise RuntimeError("line_credentials_missing")
            sender = Line(token, recipient)
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
            if args.seconds:
                loop.call_later(args.seconds, stop.set)
            receiver_task = asyncio.create_task(receiver.listen(stop)) if not args.no_receiver else None
            client = None
            next_refresh = 0
            failures = 0
            startup = True
            activated = store.get("activated_at") or time.time()
            store.put("activated_at", activated)
            event("service.started", phase="send" if args.send else "dry_run")
            if args.webhook:
                if not channel_secret or not recipient:
                    raise RuntimeError("webhook_credentials_missing")
                from aiohttp import web
                from .webhook import application
                web_runner = web.AppRunner(application(engine, channel_secret, recipient), access_log=None)
                await web_runner.setup()
                await web.TCPSite(web_runner, "127.0.0.1", args.port).start()
            while not stop.is_set():
                now = time.time()
                local = datetime.fromtimestamp(now, BANGKOK)
                day = local.date().isoformat()
                requested, completed = store.db.execute("SELECT requested,completed FROM push_refresh").fetchone()
                daily_due = local.hour >= 6 and store.get("daily_attempt") != day
                identity = store.get("identity", {})
                subscription_due = bool(identity.get("endpoint")) and store.get("published_endpoint") != identity["endpoint"]
                refresh_due = startup or requested > completed or daily_due or subscription_due or store.get("refresh_failed", False)
                if refresh_due and now >= next_refresh:
                    was_startup = startup
                    store.put("daily_attempt", day if local.hour >= 6 else store.get("daily_attempt"))
                    startup = False
                    try:
                        if client is None:
                            client = await asyncio.to_thread(login, username, password)
                        identity = store.get("identity", {})
                        if identity.get("endpoint") and (subscription_due or was_startup or daily_due):
                            sub = subscription(identity)
                            if subscription_due or not await asyncio.to_thread(client.verify, sub):
                                await asyncio.to_thread(client.publish, sub)
                            store.put("published_endpoint", identity["endpoint"])
                            store.put("verified_at", time.time())
                            event("courseville.subscription_verified")
                        courses = await asyncio.to_thread(client.assignments)
                        engine.snapshot(courses, now, requested)
                        store.put("refresh_failed", False)
                        failures = 0
                        engine.incident(False, now)
                        event("refresh.completed", count=sum(len(c["assignments"]) for c in courses))
                    except Exception as exc:
                        client = None
                        failures += 1
                        store.put("refresh_failed", True)
                        event("refresh.failed", logging.WARNING, error_type=type(exc).__name__, attempt=failures)
                        last = store.get("last_refresh", activated)
                        if now-last >= 86400 or isinstance(exc, RuntimeError) and str(exc).startswith("courseville_login"):
                            engine.incident(True, now)
                    next_refresh = time.time() + (min(3600, 60 * 2 ** min(failures, 6)) if failures else 10)
                engine.morning(time.time())
                if now-store.get("retention_at", 0) >= 86400:
                    engine.retention(now)
                if args.send:
                    for row in engine.pending(time.time()):
                        prepared = engine.prepare(row, time.time())
                        if not prepared:
                            continue
                        out_id, text, retry_key = prepared
                        try:
                            await asyncio.to_thread(sender.send, text, retry_key)
                            engine.accepted(out_id)
                            event("delivery.accepted")
                        except Exception as exc:
                            engine.failed(out_id, time.time(), isinstance(exc, DeliveryError) and exc.permanent)
                            event("delivery.failed", logging.ERROR, error_type=type(exc).__name__)
                if args.once:
                    if store.get("refresh_failed", False):
                        raise RuntimeError("one_shot_refresh_failed")
                    break
                try:
                    await asyncio.wait_for(stop.wait(), timeout=5)
                except TimeoutError:
                    pass
        finally:
            stop.set()
            if web_runner:
                await web_runner.cleanup()
            if receiver_task:
                try:
                    await asyncio.wait_for(receiver_task, timeout=10)
                except TimeoutError:
                    receiver_task.cancel()
                    await asyncio.gather(receiver_task, return_exceptions=True)
            store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("state/main.db"))
    parser.add_argument("--legacy-database", type=Path, default=Path("database/main.db"))
    parser.add_argument("--legacy-key", type=Path, default=Path("secret/private_key.pem"))
    parser.add_argument("--legacy-user", default="u1")
    parser.add_argument("--line-env", type=Path, default=Path(".env"))
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-receiver", action="store_true")
    parser.add_argument("--seconds", type=int, default=0)
    parser.add_argument("--webhook", action="store_true", help="Expose only /callback and /healthz on loopback")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    configure()
    try:
        asyncio.run(daemon(args))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        event("service.failed", logging.ERROR, error_type=type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
