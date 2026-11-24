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
    assert store.db.execute("SELECT requested,completed FROM push_refresh").fetchone() == (0, 0)
    # Even an unrelated pending refresh must not block homework.
    store.db.execute("UPDATE push_refresh SET requested=1")
    first = engine.prepare(row, now)
    assert first is not None
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
    prefs['push_other'] = False
    engine.save_preferences(prefs)
    assert engine.prepare(rows[0], 11) is None
    assert Engine(store).preferences()['push_other'] is False
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


def test_push_classification_and_independent_preferences(tmp_path):
    from mcv_service.push_types import classify_push, PUSH_TYPES
    samples = [
        ({'type': 'assignmentCreated'}, 'push_assignment'),
        ({'data': {'category': 'announcement'}}, 'push_announcement'),
        ({'notification': {'url': 'https://alpha.mycourseville.com/course/123/materials/456'}}, 'push_material'),
        ({'url': 'https://www.mycourseville.com/?q=courseville/announcement/123'}, 'push_announcement'),
        ({'title': 'Assignment material announcement'}, 'push_other'),
        ({'type': 12}, 'push_other'),
        ({'type': 'announcement', 'data': {'type': 'assignment'}}, 'push_other'),
        ({'url': 'https://evil.example/materials/123'}, 'push_other'),
        ({'url': 'http://[invalid'}, 'push_other'),
    ]
    for payload, expected in samples:
        assert classify_push(payload) == expected
    store = Store(tmp_path / 'state.db')
    engine = Engine(store)
    store.put('notification_preferences', {'courseville_push': False})
    assert all(not engine.preferences()[key] for key in PUSH_TYPES)
    prefs = engine.preferences()
    prefs['push_material'] = True
    engine.save_preferences(prefs)
    for version, payload in enumerate([{'type': 'material'}, {'type': 'announcement'}]):
        store.accept('channel', str(version), payload)
    engine.forward_pushes(10)
    engine.forward_pushes(11)
    rows = engine.pending(11)
    assert len(rows) == 2
    assert [row[1] for row in rows] == ['push_material', 'push_announcement']
    assert engine.prepare(rows[0], 11) is not None
    assert engine.prepare(rows[1], 11) is None
    assert store.db.execute('SELECT requested FROM push_refresh').fetchone() == (2,)
    store.close()


def test_homework_without_snapshot_never_refreshes(tmp_path):
    store = Store(tmp_path / 'state.db')
    engine = Engine(store)
    with store.db:
        engine.queue_homework('empty', 10)
    result = engine.prepare(engine.pending(10)[0], 10)
    assert 'No assignment data saved yet' in result[1]
    assert store.db.execute('SELECT requested,completed FROM push_refresh').fetchone() == (0, 0)
    store.close()


def test_real_courseville_assignment_pushes(tmp_path):
    """Real Pi payload shape: type lives in the q route, message is course title."""
    from mcv_service.push_types import classify_push
    store = Store(tmp_path / 'state.db')
    engine = Engine(store)
    for version, (title, assignment_id) in enumerate([
            ('HW 6 - Assignment', '2237939'), ('HW7 - Assignment', '2253920')]):
        payload = {
            'icon': 'files/thumbs/2102332_1439173699.png',
            'message': 'LINEAR CONTROL SYSTEMS I [Section 1 - 3]',
            'silent': False,
            'title': title,
            'url': 'https://www.mycourseville.com/?q=courseville/course/83503/assignment/' + assignment_id,
        }
        assert classify_push(payload) == 'push_assignment'
        # The icon's files directory must not be interpreted as a material notification.
        store.accept('real-shape', str(version), payload)
    engine.forward_pushes(10)
    rows = engine.pending(10)
    assert len(rows) == 2
    for row in rows:
        assert row[1] == 'push_assignment'
        assert 'LINEAR CONTROL SYSTEMS I' in engine.prepare(row, 10)[1]
    prefs = engine.preferences()
    prefs['push_assignment'] = False
    engine.save_preferences(prefs)
    assert all(engine.prepare(row, 11) is None for row in rows)
    store.close()


def test_real_material_and_score_pushes(tmp_path):
    from mcv_service.push_types import classify_push
    material = {
        'icon': 'https://www.mycourseville.com/sites/all/modules/courseville/files/thumbs/icon-default.png',
        'message': 'Random Processes for Electrical Engineering [Section 1]',
        'silent': False, 'title': 'exam 2 code template - Material',
        'url': 'https://www.mycourseville.com/?q=courseville/course/86788/material/2253241',
    }
    score = {
        'icon': 'https://mycourseville-default.s3.ap-southeast-1.amazonaws.com/course_icon.png',
        'message': 'Fundamental of Power Engineering Laboratory [Section 1 - 2]',
        'silent': False, 'title': 'Lab 9 - Score',
        'url': 'https://www.mycourseville.com/?q=courseville/course/83637',
    }
    assert classify_push(material) == 'push_material'
    assert classify_push(score) == 'push_score'
    assert classify_push({'title': 'Score calculation homework'}) == 'push_other'
    assert classify_push({'title': 'Lab - Score discussion'}) == 'push_other'
    assert classify_push(dict(material, title='Score - Assignment')) == 'push_assignment'
    assert classify_push({'type': 'material', 'data': {'type': 'assignment'}, 'title': 'Lab - Score'}) == 'push_score'
    store = Store(tmp_path / 'state.db')
    engine = Engine(store)
    prefs = engine.preferences()
    prefs['push_material'] = False
    engine.save_preferences(prefs)
    store.accept('samples', 'material', material)
    store.accept('samples', 'score', score)
    engine.forward_pushes(10)
    rows = engine.pending(10)
    assert [row[1] for row in rows] == ['push_material', 'push_score']
    assert engine.prepare(rows[0], 10) is None
    assert engine.prepare(rows[1], 10) is not None
    store.close()


def test_suffix_priority_and_provisional_announcement():
    from mcv_service.push_types import classify_push, PUSH_TYPES
    assert 'unverified' in PUSH_TYPES['push_announcement']
    assert classify_push({'title': 'Exam - tips - Announcement'}) == 'push_announcement'
    assert classify_push({'title': 'Homework - Material - Score'}) == 'push_score'
    assert classify_push({'title': 'Score discussion'}) == 'push_other'
    assert classify_push({'title': 'Lab - Unknown', 'url': 'https://www.mycourseville.com/?q=courseville/course/1/material/2'}) == 'push_material'
    assert classify_push({'title': 'Lab - Unknown'}) == 'push_other'
    assert classify_push({'title': 'Lab - Score', 'notification': {'title': 'Lab - Material'}}) == 'push_other'
