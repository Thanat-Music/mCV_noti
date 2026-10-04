"""Opt-in live transport proof. Uses a SEPARATE subscription and signing key.

Never claims that an application-signed probe came from CourseVille.
"""
import asyncio
import json
import tempfile
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import webpush, WebPushException

from .autopush import Receiver, encode
from .store import Store


def sender_key():
    key = ec.generate_private_key(ec.SECP256R1())
    private = encode(key.private_numbers().private_value.to_bytes(32, "big"))
    public = encode(key.public_key().public_bytes(serialization.Encoding.X962,
                                                  serialization.PublicFormat.UncompressedPoint))
    return private, public


async def next_notification(receiver, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = await receiver.receive(deadline - time.monotonic())
        if message.get("messageType") == "notification":
            return message
    raise TimeoutError("no_notification")


async def live_proof():
    private, public = sender_key()
    results = {"kind": "real_transport_own_sender", "courseville_delivery_verified": False,
               "checks": {}}
    with tempfile.TemporaryDirectory(prefix="mcv-push-proof-") as directory:
        store = Store(Path(directory) / "proof.db")
        receiver = Receiver(store, public)
        try:
            sub = await receiver.open()

            async def send(nonce, key=private):
                return await asyncio.to_thread(webpush, subscription_info=sub,
                    data=json.dumps({"probe": nonce}), vapid_private_key=key,
                    vapid_claims={"sub": "mailto:receiver-test@example.com"},
                    ttl=120, timeout=20)

            nonce = str(uuid.uuid4())
            await send(nonce)
            message = await next_notification(receiver)
            payload = await receiver.handle(message)
            if payload != {"probe": nonce}:
                raise AssertionError("online_payload_mismatch")
            results["checks"]["encrypted_online_delivery"] = True

            # Replaying the identical transport identity must not request a second refresh.
            before = store.db.execute("SELECT requested FROM push_refresh").fetchone()[0]
            await receiver.handle(message)
            after = store.db.execute("SELECT requested FROM push_refresh").fetchone()[0]
            if before != after:
                raise AssertionError("duplicate_created_refresh")
            results["checks"]["duplicate_suppressed"] = True

            wrong, _ = sender_key()
            try:
                await send("wrong-key-probe", wrong)
            except WebPushException as exc:
                if exc.response is None or exc.response.status_code not in (401, 403):
                    raise RuntimeError("unexpected_wrong_key_result") from None
                results["checks"]["wrong_sender_key_rejected"] = True
            else:
                raise AssertionError("wrong_sender_key_accepted")

            await receiver.close()
            nonce = str(uuid.uuid4())
            await send(nonce)
            # Recreate both store and receiver, not just the socket, to exercise disk state.
            store.close()
            store = Store(Path(directory) / "proof.db")
            receiver = Receiver(store, public)
            resumed = await receiver.open()
            if resumed != sub:
                raise AssertionError("subscription_changed_after_restart")
            payload = await receiver.handle(await next_notification(receiver))
            if payload != {"probe": nonce}:
                raise AssertionError("offline_payload_mismatch")
            results["checks"]["offline_delivery_after_restart"] = True
            results["checks"]["subscription_persisted"] = True

            # Simulate a crash boundary after DB commit but before acknowledgement.
            nonce = str(uuid.uuid4())
            await send(nonce)
            pending = await next_notification(receiver)
            await receiver.handle(pending, acknowledge=False)
            before = store.db.execute("SELECT requested FROM push_refresh").fetchone()[0]
            await receiver.close()
            store.close()
            store = Store(Path(directory) / "proof.db")
            receiver = Receiver(store, public)
            await receiver.open()
            replay = await next_notification(receiver)
            if replay["version"] != pending["version"]:
                raise AssertionError("unexpected_replay_version")
            payload = await receiver.handle(replay)
            after = store.db.execute("SELECT requested FROM push_refresh").fetchone()[0]
            if payload != {"probe": nonce} or before != after:
                raise AssertionError("replay_not_durable")
            results["checks"]["unacked_redelivery_after_restart"] = True
        finally:
            try:
                if receiver.ws:
                    await receiver.send({"messageType": "unregister", "channelID": receiver.identity["channel"]})
                    await receiver.expected("unregister")
            finally:
                await receiver.close()
                store.close()
    return results
