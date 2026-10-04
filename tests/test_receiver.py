import asyncio
import io
import json
import logging
import sqlite3

import http_ece
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from receiver.autopush import Receiver, MCV_VAPID, decode, encode, decrypt, new_identity
from receiver.courseville import CourseVille
from receiver.logging import event
from receiver.store import Store, ReceiverLock


def encrypted(identity, payload, version="event-1", encoding="aes128gcm"):
    key = ec.generate_private_key(ec.SECP256R1())
    body = http_ece.encrypt(json.dumps(payload).encode(), private_key=key,
        dh=decode(identity["public"]), auth_secret=decode(identity["auth"]), version=encoding)
    return {"messageType": "notification", "channelID": identity["channel"],
            "version": version, "headers": {"encoding": encoding}, "data": encode(body)}


def test_decrypt_genuine_encrypted_payload():
    identity = new_identity(MCV_VAPID)
    payload = {"title": "Homework", "message": "Unicode: \u0e01", "url": "https://www.mycourseville.com/"}
    assert decrypt(identity, encrypted(identity, payload)) == payload


def test_ack_observes_committed_inbox_and_refresh(tmp_path):
    path = tmp_path / "state.db"
    store = Store(path)
    receiver = Receiver(store)
    class Socket:
        async def send(self, raw):
            assert json.loads(raw)["messageType"] == "ack"
            other = sqlite3.connect(path)
            try:
                assert other.execute("SELECT COUNT(*) FROM push_inbox").fetchone()[0] == 1
                assert other.execute("SELECT requested FROM push_refresh").fetchone()[0] == 1
            finally:
                other.close()
    receiver.ws = Socket()
    asyncio.run(receiver.handle(encrypted(receiver.identity, {"message": "committed"})))
    store.close()


def test_storage_failure_never_acknowledges(tmp_path, monkeypatch):
    store = Store(tmp_path / "state.db")
    receiver = Receiver(store)
    sent = []
    class Socket:
        async def send(self, raw):
            sent.append(raw)
    receiver.ws = Socket()
    def fail(*args):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(store, "accept", fail)
    with pytest.raises(sqlite3.OperationalError):
        asyncio.run(receiver.handle(encrypted(receiver.identity, {})))
    assert not sent
    store.close()


def test_crash_after_commit_before_ack_replays_once(tmp_path):
    path = tmp_path / "state.db"
    store = Store(path)
    receiver = Receiver(store)
    class LostSocket:
        async def send(self, raw):
            raise ConnectionError("connection lost")
    receiver.ws = LostSocket()
    message = encrypted(receiver.identity, {"title": "example"})
    with pytest.raises(ConnectionError):
        asyncio.run(receiver.handle(message))
    store.close()
    store = Store(path)
    resumed = Receiver(store)
    asyncio.run(resumed.handle(message, acknowledge=False))
    assert store.counts() == {"pending": 1}
    assert store.db.execute("SELECT requested FROM push_refresh").fetchone() == (1,)
    store.close()


def test_identical_payload_new_transport_id_is_not_lost(tmp_path):
    store = Store(tmp_path / "state.db")
    receiver = Receiver(store)
    for version in ("one", "two"):
        asyncio.run(receiver.handle(encrypted(receiver.identity, {}, version), acknowledge=False))
    assert store.counts() == {"pending": 2}
    store.close()


def test_tamper_quarantined_and_refresh_requested(tmp_path):
    store = Store(tmp_path / "state.db")
    receiver = Receiver(store)
    message = encrypted(receiver.identity, {"title": "valid"})
    raw = bytearray(decode(message["data"]))
    raw[-1] ^= 1
    message["data"] = encode(raw)
    result = asyncio.run(receiver.handle(message, acknowledge=False))
    assert result == {"error": "invalid_push_payload"}
    assert store.counts() == {"quarantined": 1}
    assert store.db.execute("SELECT requested FROM push_refresh").fetchone() == (1,)
    store.close()


def test_unknown_channel_not_accepted(tmp_path):
    store = Store(tmp_path / "state.db")
    receiver = Receiver(store)
    message = encrypted(receiver.identity, {})
    message["channelID"] = "another-account"
    with pytest.raises(ValueError):
        asyncio.run(receiver.handle(message, acknowledge=False))
    assert store.counts() == {}
    store.close()


def test_identity_mismatch_fails_without_overwriting(tmp_path):
    store = Store(tmp_path / "state.db")
    original = Receiver(store).identity.copy()
    wrong = new_identity(MCV_VAPID)["public"]
    with pytest.raises(RuntimeError):
        Receiver(store, wrong)
    assert store.get("identity") == original
    store.close()


def test_receiver_lock_prevents_concurrent_identity_use(tmp_path):
    path = tmp_path / "state.db"
    with ReceiverLock(path):
        with pytest.raises(RuntimeError):
            with ReceiverLock(path):
                pass
    with ReceiverLock(path):
        pass


class Response:
    status_code = 200
    def __init__(self, value):
        self.value = value
    def json(self):
        return self.value


def test_publish_requires_check_and_list_agreement():
    class Session:
        def request(self, method, url, **kwargs):
            if url.endswith("publish"):
                return Response({"success": True})
            if url.endswith("list"):
                return Response({"success": True, "subscriptions": []})
            return Response({"subscribed": True})
    with pytest.raises(RuntimeError):
        CourseVille(Session()).publish({"endpoint": "https://example.com/test"})


def test_login_html_is_not_success():
    class Session:
        def request(self, *args, **kwargs):
            return Response("<html>login</html>")
    with pytest.raises(RuntimeError):
        CourseVille(Session()).call("list")


def test_logging_drops_sensitive_fields():
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    logger = logging.getLogger("mcv.receiver")
    old_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        event("test.safe", password="SECRET", payload={"auth": "SECRET"},
              endpoint="https://secret.example/SECRET", count=2)
        assert "SECRET" not in buffer.getvalue()
        assert json.loads(buffer.getvalue())["count"] == 2
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)


def test_log_overload_is_bounded_and_nonblocking():
    import threading
    from receiver.logging import BoundedHandler
    entered, release = threading.Event(), threading.Event()
    class SlowSink(logging.Handler):
        def emit(self, record):
            entered.set()
            release.wait(2)
    handler = BoundedHandler(SlowSink(), capacity=2)
    record = logging.LogRecord("test", logging.INFO, "", 1, "safe", (), None)
    try:
        handler.handle(record)
        assert entered.wait(1)
        for _ in range(20):
            handler.handle(record)
        assert handler.queue.qsize() == 2
        assert handler.dropped == 18
    finally:
        release.set()
        handler.close()
