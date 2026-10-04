"""Small allowlisted event logger. Never stringify remote exceptions or payloads."""
import atexit
import queue
import threading
import json
import logging
from datetime import datetime, timezone

FIELDS = {"attempt", "delay_s", "count", "duration_ms", "error_type", "status", "phase"}


def event(name, level=logging.INFO, **fields):
    record = {"time": datetime.now(timezone.utc).isoformat(), "event": name,
              "level": logging.getLevelName(level)}
    record.update({k: v for k, v in fields.items()
                   if k in FIELDS and isinstance(v, (str, int, float, bool, type(None)))})
    logging.getLogger("mcv.receiver").log(level, json.dumps(record, ensure_ascii=True))


class BoundedHandler(logging.Handler):
    """Diagnostic loss is preferable to blocking durable notification processing."""
    def __init__(self, sink, capacity=1024):
        super().__init__()
        self.sink = sink
        self.queue = queue.Queue(maxsize=capacity)
        self.dropped = 0
        self.stopping = threading.Event()
        self.worker = threading.Thread(target=self._drain, daemon=True, name="diagnostic-log")
        self.worker.start()

    def emit(self, record):
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1

    def _drain(self):
        while not self.stopping.is_set() or not self.queue.empty():
            try:
                record = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self.sink.handle(record)
            except Exception:
                pass
            finally:
                self.queue.task_done()

    def close(self):
        self.stopping.set()
        self.worker.join(timeout=1)
        super().close()


def configure():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("mcv.receiver")
    for previous in logger.handlers:
        previous.close()
    queued = BoundedHandler(handler)
    logger.handlers[:] = [queued]
    atexit.register(queued.close)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # Third-party wire debugging can expose endpoints and keys.
    logging.getLogger("websockets").setLevel(logging.CRITICAL)
