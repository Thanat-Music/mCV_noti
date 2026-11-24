import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime

from aiohttp.test_utils import TestClient, TestServer
from receiver.store import Store
from mcv_service.engine import Engine, BANGKOK, NOTIFICATION_TYPES, DAY
from mcv_service.flex import assignment_messages
from mcv_service.webhook import application
from mcv_service.line import Line


def test_week_boundaries_submissions_and_flex(tmp_path):
    store = Store(tmp_path / 'test.db')
    engine = Engine(store)
    now = datetime(2026, 11, 24, 12, tzinfo=BANGKOK).timestamp()
    start = now - 12 * 3600
    assignments = [dict(id=str(i), title='A "quoted" homework', status=status,
                        dueDate=datetime.fromtimestamp(due, BANGKOK).isoformat())
                   for i, (due, status) in enumerate([(start-1, 'ASSIGNED'),
                       (start, 'OVERDUE'), (start+7*DAY+86399, 'SUBMITTED'),
                       (start+8*DAY, 'ASSIGNED')])]
    engine.snapshot([dict(courseID='course', title='Control', assignments=assignments)], now)
    items = engine.homework(now)
    assert len(items) == 2
    messages = assignment_messages(items, 'Homework', now)
    assert messages[0]['type'] == 'flex'
    raw = json.dumps(messages)
    assert '#4d0000' in raw and '<TIME_LEFT>' not in raw
    assert 'Submitted' in raw and 'Overdue' in raw
    with store.db:
        engine.queue_homework('event', now)
    row = next(r for r in engine.pending(now) if r[1] == 'homework')
    assert engine.prepare(row, now) is None
    engine.snapshot([dict(courseID='course', title='Control', assignments=assignments)], now, 1)
    first = engine.prepare(row, now)
    second = engine.prepare(next(r for r in engine.pending(now) if r[1] == 'homework'), now+60)
    assert first == second
    store.close()


def test_preferences_and_raw_push_dedup(tmp_path):
    store = Store(tmp_path / 'test.db')
    engine = Engine(store)
    store.accept('channel', '1', {'title': 'Announcement', 'body': 'New material'})
    engine.forward_pushes(10)
    engine.forward_pushes(11)
    rows = engine.pending(11)
    assert len(rows) == 1
    prefs = engine.preferences()
    prefs['courseville_push'] = False
    engine.save_preferences(prefs)
    assert engine.prepare(rows[0], 11) is None
    assert Engine(store).preferences()['courseville_push'] is False
    store.close()


def test_settings_authorization_and_signed_commands(tmp_path):
    async def scenario():
        store = Store(tmp_path / 'test.db')
        engine = Engine(store)
        client = TestClient(TestServer(application(engine, 'secret', 'me')))
        await client.start_server()
        try:
            assert (await client.get('/settings')).status == 403
            async def command(value, event_id):
                body = json.dumps({'events': [dict(webhookEventId=event_id, type='message',
                    source={'userId': 'me'}, message={'type': 'text', 'text': value})]}).encode()
                sig = base64.b64encode(hmac.new(b'secret', body, hashlib.sha256).digest()).decode()
                return await client.post('/callback', data=body, headers={'X-Line-Signature': sig})
            assert (await command('settings', 's1')).status == 200
            text = store.db.execute("SELECT text FROM app_outbox WHERE kind='command'").fetchone()[0]
            token = text.split('?token=')[1]
            # Keep a local test cookie; production links set Secure on Cloudflare.
            assert (await client.get('/settings?token=' + token)).status == 200
            assert (await client.post('/settings', data={})).status == 403
            response = await client.post('/settings', data={'csrf': token, 'new_assignment': 'on'})
            assert response.status == 200 and 'Settings saved' in await response.text()
            assert engine.preferences()['new_assignment'] is True
            assert engine.preferences()['deadline_summary'] is False
            assert (await command(' HOMEWORK ', 'h1')).status == 200
            assert (await command('homework', 'h1')).status == 200
            assert store.db.execute("SELECT COUNT(*) FROM app_outbox WHERE kind='homework'").fetchone()[0] == 1
            assert (await client.get('/settings?token=' + token[:-1] + 'x')).status == 403
        finally:
            await client.close()
            store.close()
    asyncio.run(scenario())


def test_flex_delivery_batches_stable_keys():
    class Response:
        status_code = 200
    class Session:
        def __init__(self): self.calls = []
        def post(self, *args, **kwargs):
            self.calls.append(kwargs)
            return Response()
    session = Session()
    line = Line('token', 'me', session)
    messages = [{'type': 'text', 'text': str(i)} for i in range(7)]
    key = '00000000-0000-4000-8000-000000000001'
    line.send(messages, key)
    line.send(messages, key)
    assert [len(c['json']['messages']) for c in session.calls] == [5, 2, 5, 2]
    assert session.calls[0]['headers'] == session.calls[2]['headers']
