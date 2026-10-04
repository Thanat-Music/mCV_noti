"""Own one cloudflared process and reconcile LINE's URL for that generation."""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import re
import signal
import subprocess

import aiohttp
from dotenv import dotenv_values
from receiver.logging import configure, event
from receiver.store import ReceiverLock

URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com(?![a-z0-9.:-])")
API = "https://api.line.me/v2/bot/channel/webhook/"


def candidate(line):
    match = URL_PATTERN.search(line)
    return match.group(0) if match else None


async def reconcile(session, endpoint, alive):
    async def call(method, path, body=None):
        if not alive():
            raise RuntimeError("stale_tunnel_generation")
        async with session.request(method, API+path, json=body) as response:
            if response.status != 200:
                raise RuntimeError("line_webhook_http_" + str(response.status))
            result = await response.json()
        if not alive():
            raise RuntimeError("stale_tunnel_generation")
        return result
    tested = await call("POST", "test", {"endpoint": endpoint})
    if tested.get("success") is not True:
        raise RuntimeError("line_webhook_test_failed")
    current = await call("GET", "endpoint")
    if current.get("endpoint") != endpoint:
        await call("PUT", "endpoint", {"endpoint": endpoint})
    current = await call("GET", "endpoint")
    if current.get("endpoint") != endpoint or current.get("active") is not True:
        raise RuntimeError("line_webhook_inactive_or_mismatched")
    if (await call("POST", "test", {"endpoint": endpoint})).get("success") is not True:
        raise RuntimeError("line_webhook_final_test_failed")


def write_status(path, ready, generation):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"ready": ready, "generation": generation}), encoding="utf-8")
    os.replace(temp, path)


async def run(args):
    token = dotenv_values(args.line_env).get("CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("line_token_missing")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
    generation = 0
    with ReceiverLock(args.status):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as health, \
                aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                    headers={"Authorization": "Bearer " + token}) as line:
            while not stop.is_set():
                process = None
                reader = None
                generation += 1
                write_status(args.status, False, generation)
                try:
                    async with health.get("http://127.0.0.1:8080/healthz") as response:
                        if response.status != 200:
                            raise RuntimeError("local_app_not_ready")
                    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
                    process = await asyncio.create_subprocess_exec(args.cloudflared, "tunnel", "--url", "http://127.0.0.1:8080",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, **kwargs)
                    discovered = loop.create_future()
                    async def drain():
                        while raw := await process.stdout.readline():
                            url = candidate(raw.decode("utf-8", "replace"))
                            if url and not discovered.done():
                                discovered.set_result(url)
                        if not discovered.done():
                            discovered.set_exception(RuntimeError("tunnel_exited_before_url"))
                    reader = asyncio.create_task(drain())
                    endpoint = (await asyncio.wait_for(discovered, 60)) + "/callback"
                    attempt = 0
                    while not stop.is_set() and process.returncode is None:
                        try:
                            await reconcile(line, endpoint, lambda: process.returncode is None and not stop.is_set())
                            write_status(args.status, True, generation)
                            event("line.ingress_ready")
                            attempt = 0
                            delay = 300
                        except Exception as exc:
                            write_status(args.status, False, generation)
                            attempt += 1
                            delay = min(300, 5 * 2 ** min(attempt, 6))
                            event("line.webhook_retry", logging.WARNING, error_type=type(exc).__name__, attempt=attempt)
                        # Wake promptly if cloudflared exits rather than waiting for next reconciliation.
                        exit_task = asyncio.create_task(process.wait())
                        stop_task = asyncio.create_task(stop.wait())
                        done, pending = await asyncio.wait([exit_task, stop_task], timeout=delay,
                                                           return_when=asyncio.FIRST_COMPLETED)
                        for task in pending:
                            task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        if done:
                            break
                except Exception as exc:
                    event("tunnel.failed", logging.WARNING, error_type=type(exc).__name__)
                finally:
                    write_status(args.status, False, generation)
                    if process and process.returncode is None:
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), 10)
                        except TimeoutError:
                            process.kill()
                            await process.wait()
                    if reader:
                        reader.cancel()
                        await asyncio.gather(reader, return_exceptions=True)
                if not stop.is_set():
                    try:
                        await asyncio.wait_for(stop.wait(), 15)
                    except TimeoutError:
                        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--line-env", type=Path, required=True)
    parser.add_argument("--status", type=Path, default=Path("state/ingress.json"))
    parser.add_argument("--cloudflared", default="cloudflared")
    args = parser.parse_args()
    configure()
    os.umask(0o077)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        event("tunnel.manager_failed", logging.ERROR, error_type=type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
