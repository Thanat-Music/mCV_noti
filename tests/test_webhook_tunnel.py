import asyncio
import base64
import hashlib
import hmac
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer
from mcv_service.engine import Engine
from mcv_service.webhook import application
from mcv_service.tunnel import candidate, reconcile
from receiver.store import Store


def test_webhook_signature_empty_events_and_duplicate(tmp_path):
    async def scenario():
        store = Store(tmp_path / "state.db")
        engine = Engine(store)
        client = TestClient(TestServer(application(engine, "secret", "personal-user")))
        await client.start_server()
        try:
            async def send(data, valid=True):
                raw = json.dumps(data).encode()
                sig = base64.b64encode(hmac.new(b"secret", raw, hashlib.sha256).digest()).decode()
                return await client.post("/callback", data=raw, headers={"X-Line-Signature": sig if valid else "wrong"})
            assert (await send({"events": []})).status == 200
            assert (await send({"events": []}, False)).status == 400
            message = {"events": [{"webhookEventId": "id-1", "type": "message",
                "source": {"userId": "personal-user"}, "message": {"type": "text", "text": "status"}}]}
            assert (await send(message)).status == 200
            assert (await send(message)).status == 200
            assert store.db.execute("SELECT COUNT(*) FROM app_outbox").fetchone() == (1,)
            message["events"][0]["source"]["userId"] = "stranger"
            message["events"][0]["webhookEventId"] = "id-2"
            assert (await send(message)).status == 200
            assert store.db.execute("SELECT COUNT(*) FROM app_outbox").fetchone() == (1,)
        finally:
            await client.close()
            store.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("line", ["https://foo.trycloudflare.com.evil.org", "http://foo.trycloudflare.com", "https://foo.trycloudflare.com:443"])
def test_reject_bad_tunnel_url(line):
    assert candidate(line) is None


def test_valid_tunnel_url():
    assert candidate("| https://some-random-name.trycloudflare.com |") == "https://some-random-name.trycloudflare.com"


class Response:
    def __init__(self, value):
        self.value, self.status = value, 200
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def json(self):
        return self.value


def test_tunnel_tests_before_update_and_verifies_active():
    endpoint = "https://test.trycloudflare.com/callback"
    class Session:
        calls = []
        current = "https://old.example/callback"
        def request(self, method, url, json=None):
            self.calls.append((method, url))
            if url.endswith("test"):
                return Response({"success": True})
            if method == "PUT":
                self.current = json["endpoint"]
                return Response({})
            return Response({"endpoint": self.current, "active": True})
    session = Session()
    asyncio.run(reconcile(session, endpoint, lambda: True))
    assert [method for method, url in session.calls] == ["POST", "GET", "PUT", "GET", "POST"]


def test_dead_tunnel_cannot_overwrite_line_endpoint():
    class Session:
        def request(self, *args, **kwargs):
            raise AssertionError("stale operation reached network")
    with pytest.raises(RuntimeError):
        asyncio.run(reconcile(Session(), "https://test.trycloudflare.com/callback", lambda: False))
