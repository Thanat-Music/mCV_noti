"""Mozilla Autopush adapter. Experimental external protocol, not a supported SDK.

Wire protocol reference: mozilla-services/autopush-rs tests/integration/
async_push_test_client.py. Web Push encryption is RFC 8291 via http_ece.
"""
import asyncio
import base64
import json
import logging
import os
import random
import time
import uuid
from urllib.parse import urlsplit

import http_ece
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from websockets.asyncio.client import connect

from .logging import event

MOZILLA_URL = "wss://push.services.mozilla.com/"
MCV_VAPID = "BPsnTyKxrm7XN9hIf6NroauGAPxCocHsWtga5cOsOdYGTPCR9fWUcG2DAfUd_XXf3IP-Rv3zWRm005NagUU7YKA"


def encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def decode(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def new_identity(vapid):
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decode(vapid))
    key = ec.generate_private_key(ec.SECP256R1())
    return {"vapid": vapid, "channel": str(uuid.uuid4()), "uaid": None,
            "endpoint": None,
            "private": key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode(),
            "public": encode(key.public_key().public_bytes(serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint)), "auth": encode(os.urandom(16))}


def subscription(identity):
    if not identity.get("endpoint"):
        raise RuntimeError("subscription_not_registered")
    return {"endpoint": identity["endpoint"], "expirationTime": None,
            "keys": {"p256dh": identity["public"], "auth": identity["auth"]}}


def decrypt(identity, message):
    if not message.get("data"):
        return {}
    headers = {k.lower(): v for k, v in message.get("headers", {}).items()}
    encoding = headers.get("encoding", headers.get("content-encoding", "aes128gcm"))
    kwargs = {}
    if encoding == "aesgcm":
        # Older Web Push senders carry the salt and ephemeral key in headers.
        for header, field, parameter in [("encryption", "salt", "salt"),
                                          ("crypto_key", "dh", "dh")]:
            value = headers.get(header, headers.get(header.replace("_", "-"), ""))
            parts = dict(p.strip().split("=", 1) for p in value.split(";") if "=" in p)
            kwargs[parameter] = decode(parts[field].strip('"'))
    elif encoding != "aes128gcm":
        raise ValueError("unsupported_encoding")
    private = serialization.load_pem_private_key(identity["private"].encode(), password=None)
    raw = http_ece.decrypt(decode(message["data"]), private_key=private,
                           auth_secret=decode(identity["auth"]), version=encoding, **kwargs)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("payload_not_object")
    return value


class Receiver:
    def __init__(self, store, vapid=MCV_VAPID, url=MOZILLA_URL):
        self.store = store
        self.url = url
        self.identity = store.get("identity")
        if self.identity is None:
            self.identity = new_identity(vapid)
            self.save()
        if self.identity["vapid"] != vapid:
            raise RuntimeError("vapid_mismatch_use_separate_database")
        self.ws = None

    def save(self):
        self.store.put("identity", self.identity)

    async def send(self, value):
        await self.ws.send(json.dumps(value))

    async def receive(self, timeout=30):
        value = json.loads(await asyncio.wait_for(self.ws.recv(), timeout))
        if not isinstance(value, dict):
            raise ValueError("invalid_protocol_frame")
        return value

    async def expected(self, kind):
        deadline = time.monotonic() + 30
        while True:
            message = await self.receive(max(0.1, deadline - time.monotonic()))
            if message.get("messageType") == kind:
                if message.get("status") != 200:
                    raise RuntimeError("push_service_rejected_" + kind)
                return message
            if message.get("messageType") == "notification":
                await self.handle(message)
            if time.monotonic() >= deadline:
                raise TimeoutError("handshake_timeout")

    async def open(self):
        self.ws = await connect(self.url, open_timeout=20, close_timeout=5,
                                ping_interval=120, ping_timeout=30, max_size=65536)
        hello = {"messageType": "hello", "use_webpush": True,
                 "channelIDs": [self.identity["channel"]] if self.identity["endpoint"] else []}
        if self.identity["uaid"]:
            hello["uaid"] = self.identity["uaid"]
        await self.send(hello)
        reply = await self.expected("hello")
        if not isinstance(reply.get("uaid"), str):
            raise ValueError("missing_uaid")
        if reply["uaid"] != self.identity["uaid"]:
            self.identity.update(uaid=reply["uaid"], endpoint=None)
            self.save()
        if not self.identity["endpoint"]:
            await self.send({"messageType": "register", "channelID": self.identity["channel"],
                             "key": self.identity["vapid"]})
            reply = await self.expected("register")
            endpoint = reply.get("pushEndpoint", "")
            if reply.get("channelID") != self.identity["channel"] or urlsplit(endpoint).scheme != "https":
                raise ValueError("invalid_registration")
            self.identity["endpoint"] = endpoint
            self.save()
            event("subscription.registered")
        self.store.put("connected_at", time.time())
        event("receiver.connected")
        return subscription(self.identity)

    async def handle(self, message, acknowledge=True):
        if message.get("channelID") != self.identity["channel"] or "version" not in message:
            raise ValueError("unknown_notification_channel")
        state = "pending"
        try:
            payload = decrypt(self.identity, message)
        except (ValueError, KeyError, http_ece.ECEException):
            # Retain minimal failure evidence, not the secret ciphertext or exception text.
            payload, state = {"error": "invalid_push_payload"}, "quarantined"
            event("push.invalid_payload", logging.ERROR)
        inserted = self.store.accept(self.identity["channel"], message["version"], payload, state)
        if acknowledge:
            await self.send({"messageType": "ack", "updates": [{
                "channelID": self.identity["channel"], "version": message["version"], "code": 100}]})
        event("push.accepted" if inserted else "push.duplicate")
        return payload

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.ws = None

    async def listen(self, stop):
        attempt = 0
        while not stop.is_set():
            started = time.monotonic()
            try:
                await self.open()
                while not stop.is_set():
                    try:
                        message = await self.receive(timeout=5)
                    except TimeoutError:
                        continue
                    if message.get("messageType") == "notification":
                        await self.handle(message)
            except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
                event("receiver.disconnected", logging.WARNING, error_type=type(exc).__name__)
            except Exception as exc:
                # Third-party connection/crypto errors are sanitized, never dumped with tokens.
                event("receiver.failed", logging.ERROR, error_type=type(exc).__name__)
            finally:
                await self.close()
            attempt = 0 if time.monotonic() - started >= 120 else min(attempt + 1, 8)
            delay = min(300, 2 ** attempt) + random.random()
            if not stop.is_set():
                event("receiver.retry", attempt=attempt, delay_s=round(delay, 2))
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                except TimeoutError:
                    pass
