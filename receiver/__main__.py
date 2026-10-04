import argparse
import asyncio
import getpass
import json
import os
from pathlib import Path
import signal
import sys
import time

from .autopush import Receiver, subscription
from .logging import configure, event
from .store import Store, ReceiverLock


async def run(args, store):
    receiver = Receiver(store)
    if args.command == "register":
        try:
            await receiver.open()
            event("receiver.registered_locally")
        finally:
            await receiver.close()
    elif args.command == "listen":
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
        if args.seconds:
            loop.call_later(args.seconds, stop.set)
        await receiver.listen(stop)
    elif args.command in ("publish", "verify"):
        from .courseville import login, legacy_account
        # Only publish an already registered identity; no unnecessary socket churn.
        sub = subscription(receiver.identity)
        if args.legacy_user:
            username, password = legacy_account(args.legacy_database, args.legacy_key, args.legacy_user)
        else:
            username = getpass.getpass("CourseVille username (hidden): ")
            password = getpass.getpass("CourseVille password: ")
        client = await asyncio.to_thread(login, username, password)
        if args.command == "publish":
            await asyncio.to_thread(client.publish, sub)
            store.put("published_endpoint", sub["endpoint"])
        elif not await asyncio.to_thread(client.verify, sub):
            raise RuntimeError("courseville_subscription_missing")
        store.put("verified_at", time.time())
        event("courseville.subscription_verified")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Experimental standalone CourseVille push receiver")
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("MCV_DATABASE", "state/main.db")))
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("register", "status", "proof"):
        commands.add_parser(name)
    for name in ("publish", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--legacy-user", help="Explicit local database account; no secret values in arguments")
        command.add_argument("--legacy-database", type=Path, default=Path("database/main.db"))
        command.add_argument("--legacy-key", type=Path, default=Path("secret/private_key.pem"))
    listen = commands.add_parser("listen")
    listen.add_argument("--seconds", type=int, default=0, help="0 = run until interrupted")
    args = parser.parse_args()
    configure()
    try:
        if args.command == "proof":
            from .proof import live_proof
            print(json.dumps(asyncio.run(live_proof()), indent=2))
            return
        if args.command == "status":
            print(json.dumps(Store.status(args.database), indent=2))
            return
        with ReceiverLock(args.database):
            store = Store(args.database)
            try:
                asyncio.run(run(args, store))
            finally:
                store.close()
    except KeyboardInterrupt:
        return
    except Exception as exc:
        event("command.failed", 40, error_type=type(exc).__name__)
        print("Operation failed; see sanitized event. No credential or remote response was printed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
