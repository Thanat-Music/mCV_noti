"""One event-driven outbox sender per account, independent of refresh work."""
import asyncio
import logging
import time

from receiver.logging import event


async def deliver_pending(engine, sender, stop):
    for row in engine.pending(time.time()):
        if stop.is_set():
            break
        prepared = engine.prepare(row, time.time())
        if not prepared:
            continue
        out_id, text, retry_key = prepared
        try:
            messages = engine.delivery_messages(out_id, text, time.time())
            await asyncio.to_thread(sender.send, messages, retry_key)
            engine.accepted(out_id)
            event("delivery.accepted")
        except Exception as exc:
            engine.failed(out_id, time.time(), getattr(exc, "permanent", False))
            event("delivery.failed", logging.ERROR, error_type=type(exc).__name__,
                  status=getattr(exc, "status", None))


async def delivery_worker(engine, sender, stop):
    # Startup drains durable work; the timeout discovers retries after backoff.
    while not stop.is_set():
        engine.delivery_ready.clear()
        await deliver_pending(engine, sender, stop)
        if engine.pending(time.time()):
            continue
        ready = asyncio.create_task(engine.delivery_ready.wait())
        stopped = asyncio.create_task(stop.wait())
        try:
            await asyncio.wait((ready, stopped), timeout=5,
                               return_when=asyncio.FIRST_COMPLETED)
        finally:
            ready.cancel()
            stopped.cancel()
            await asyncio.gather(ready, stopped, return_exceptions=True)
