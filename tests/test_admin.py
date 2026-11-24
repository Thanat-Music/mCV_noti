"""Admin isolation, signup binding and encrypted credential behaviour."""
import base64
import hashlib
import hmac
import json
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import web
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from yarl import URL

from receiver.courseville import legacy_account
from receiver.store import Store
from mcv_service.accounts import Accounts
from mcv_service.admin import application as admin_app
from mcv_service.dashboard import read_snapshot
from mcv_service.enrollment import Enrollment
from mcv_service.engine import Engine, NOTIFICATION_TYPES
from mcv_service.supervisor import Workers
from mcv_service.webhook import application


def immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError('Unexpected asynchronous IO in handler unit test')


def registry(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / 'key.pem'
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return Accounts(tmp_path / 'main.db', key_path), key_path


def account_values(line='U'+'1'*32):
    return {'label': 'Test account', 'username': 'student', 'password': 'private-pass', 'line_id': line, 'enabled': False}


def test_account_lifecycle_and_encryption(tmp_path):
    accounts, key_path = registry(tmp_path)
    user = accounts.save(account_values())
    assert 'password' not in user and 'username' not in user
    assert legacy_account(accounts.database, key_path, user['id']) == ('student', 'private-pass')
    try:
        accounts.save({'username':'another-student','password':'different'}, user['id'])
    except ValueError:
        pass
    else:
        raise AssertionError('CourseVille identity change could reuse another account cache')
    cipher = accounts.db.execute('SELECT cname,cpass FROM user WHERE user_id=?', (user['id'],)).fetchone()
    assert cipher[0] != 'student' and cipher[1] != 'private-pass'
    accounts.save({'label': 'Changed', 'enabled': True}, user['id'])
    assert accounts.get(user['id'])['revision'] == 2
    assert accounts.db.execute('SELECT cname,cpass FROM user WHERE user_id=?', (user['id'],)).fetchone() == cipher
    try:
        accounts.save(account_values())
    except ValueError:
        pass
    else:
        raise AssertionError('Duplicate LINE recipient allowed')
    history = accounts.state_path(accounts.database, user['id'])
    history.parent.mkdir(exist_ok=True)
    history.write_bytes(b'preserved history')
    accounts.delete(user['id'])
    assert accounts.get(user['id']) is None
    assert accounts.db.execute('SELECT COUNT(*) FROM user').fetchone()[0] == 0
    assert history.read_bytes() == b'preserved history'
    assert accounts.audit()[0]['action'] == 'user.deleted'
    try:
        accounts.state_path(accounts.database, '../escape')
    except ValueError:
        pass
    else:
        raise AssertionError('Unsafe account path allowed')
    accounts.close()


def test_signup_sender_binding_expiry_and_approval(tmp_path):
    accounts, key_path = registry(tmp_path)
    enrollment = Enrollment(accounts, 'channel-secret')
    recipient = 'U'+'2'*32
    token = enrollment.invite(recipient, 'event-1')
    assert token == enrollment.invite(recipient, 'event-1')
    assert enrollment.valid(token) == recipient
    assert enrollment.valid(token, time.time()+901) is None
    assert enrollment.valid('x'*64) is None
    user = enrollment.register(token, 'Student', 'student', 'private-pass')
    assert user['line_id'] == recipient and not user['enabled'] and not user['approved']
    assert enrollment.valid(token) is None
    accounts.save({'enabled': True}, user['id'])
    assert accounts.get(user['id'])['approved'] and accounts.get(user['id'])['enabled']
    assert legacy_account(accounts.database, key_path, user['id']) == ('student', 'private-pass')
    enrollment.queue(recipient, 'event-1', 'signup link')
    enrollment.queue(recipient, 'event-1', 'duplicate')
    assert accounts.db.execute('SELECT COUNT(*) FROM admin_signup_outbox').fetchone()[0] == 1
    accounts.close()


def test_per_user_snapshot_excludes_secrets(tmp_path):
    accounts, _ = registry(tmp_path)
    one = accounts.save(account_values())
    two = accounts.save(account_values('U'+'2'*32))
    p1, p2 = (accounts.state_path(accounts.database, user['id']) for user in (one, two))
    assert p1 != p2 and accounts.state_path(accounts.database, 'u1') == accounts.database
    for path, title in ((p1, 'Only user one'), (p2, 'Only user two')):
        store = Store(path)
        engine = Engine(store)
        store.put('identity', {'private': 'must-not-return'})
        engine.snapshot([{'courseID':'c', 'title':'Course', 'assignments':[{'id':'a', 'title':title, 'status':'ASSIGNED', 'dueDate':None}]}], 10)
        store.close()
    raw = json.dumps(read_snapshot(p1, 10))
    assert 'Only user one' in raw and 'Only user two' not in raw
    assert 'must-not-return' not in raw and 'private-pass' not in raw
    accounts.close()


def test_settings_tokens_cannot_cross_users(tmp_path):
    stores = [Store(tmp_path / (name+'.db')) for name in ('one', 'two')]
    apps = [application(Engine(store), 'secret', 'U'+'1'*32, '/settings/'+name)
            for store, name in zip(stores, ('one', 'two'))]
    body = json.dumps({'events':[{'webhookEventId':'s1','type':'message', 'source':{'userId':'U'+'1'*32},
                                 'message':{'type':'text','text':'settings'}}]}).encode()
    signature = base64.b64encode(hmac.new(b'secret', body, hashlib.sha256).digest()).decode()
    req = SimpleNamespace(read=AsyncMock(return_value=body), headers={'X-Line-Signature':signature},
                          url=URL('https://example.trycloudflare.com/callback'))
    routes = lambda app: {(r.method,r.resource.canonical):r.handler for r in app.router.routes()}
    assert immediate(routes(apps[0])['POST','/callback'](req)).status == 200
    link = stores[0].db.execute('SELECT text FROM app_outbox').fetchone()[0]
    assert '/settings/one?token=' in link
    token = link.split('?token=')[1]
    request = SimpleNamespace(query={'token':token}, cookies={}, method='GET', scheme='https',host='example.trycloudflare.com')
    assert immediate(routes(apps[0])['GET','/settings/one'](request)).status == 303
    try:
        immediate(routes(apps[1])['GET','/settings/two'](request))
    except web.HTTPForbidden:
        pass
    else:
        raise AssertionError('Settings token accepted for another user')
    for store in stores:
        store.close()


def test_public_start_dedup_and_admin_guards(tmp_path):
    accounts, _ = registry(tmp_path)
    args = SimpleNamespace(database=accounts.database, send=False)
    workers = Workers(args, accounts)
    public = workers.public_app('secret')
    routes = {(r.method,r.resource.canonical):r.handler for r in public.router.routes()}
    body = json.dumps({'events':[{'webhookEventId':'start-1','type':'message','source':{'userId':'U'+'3'*32},
                                 'message':{'type':'text','text':'start'}}]}).encode()
    signature = base64.b64encode(hmac.new(b'secret', body, hashlib.sha256).digest()).decode()
    req = SimpleNamespace(read=AsyncMock(return_value=body),headers={'X-Line-Signature':signature},url=URL('https://example.trycloudflare.com/callback'))
    assert immediate(routes['POST','/callback'](req)).status == 200
    assert immediate(routes['POST','/callback'](req)).status == 200
    assert accounts.db.execute('SELECT COUNT(*) FROM admin_signup_outbox').fetchone()[0] == 1
    req.headers={'X-Line-Signature':'invalid'}
    try:
        immediate(routes['POST','/callback'](req))
    except web.HTTPBadRequest:
        pass
    else:
        raise AssertionError('Unsigned registration accepted')
    admin = admin_app(accounts, workers, args)
    guard = admin.middlewares[0]
    good = SimpleNamespace(host='localhost:8081',headers={},method='GET')
    async def handler(request):
        return web.Response(text='OK')
    assert immediate(guard(good,handler)).status == 200
    for request in (SimpleNamespace(host='evil.example:8081',headers={},method='GET'),
                    SimpleNamespace(host='localhost:8081',headers={},method='POST')):
        try:
            immediate(guard(request,handler))
        except web.HTTPForbidden:
            pass
        else:
            raise AssertionError('Admin guard bypassed')
    accounts.close()


def test_multiuser_callback_routes_only_to_matching_account(tmp_path):
    accounts, _ = registry(tmp_path)
    one = accounts.save(dict(account_values(), enabled=True))
    two = accounts.save(dict(account_values('U'+'2'*32), enabled=True))
    workers = Workers(SimpleNamespace(database=accounts.database, send=False), accounts)
    public = workers.public_app('secret')
    stores = []
    for user in (one, two):
        store = Store(accounts.state_path(accounts.database, user['id']))
        stores.append(store)
        engine = Engine(store)
        workers.running[user['id']] = {'engine':engine,'recipient':user['line_id'],
            'task':SimpleNamespace(done=lambda:False),
            'app':application(engine,'secret',user['line_id'],'/settings/'+user['id'])}
    callback = next(route.handler for route in public.router.routes() if route.resource.canonical=='/callback')
    payload = {'events':[{'webhookEventId':'only-two','type':'message','source':{'userId':two['line_id']},
                         'message':{'type':'text','text':'homework'}}]}
    body = json.dumps(payload).encode()
    signature = base64.b64encode(hmac.new(b'secret',body,hashlib.sha256).digest()).decode()
    request = SimpleNamespace(read=AsyncMock(return_value=body),headers={'X-Line-Signature':signature},url=URL('https://example.trycloudflare.com/callback'))
    immediate(callback(request))
    immediate(callback(request))
    assert stores[0].db.execute('SELECT COUNT(*) FROM app_outbox').fetchone()[0] == 0
    assert stores[1].db.execute("SELECT COUNT(*) FROM app_outbox WHERE kind='homework'").fetchone()[0] == 1
    assert stores[1].db.execute('SELECT requested FROM push_refresh').fetchone()[0] == 0
    for store in stores:
        store.close()
    accounts.close()


def test_admin_mutations_and_secret_free_responses(tmp_path):
    import asyncio
    import re
    accounts, _ = registry(tmp_path)
    workers = SimpleNamespace(running={}, errors={}, lock=asyncio.Lock(), stop=AsyncMock(), reconcile=AsyncMock())
    app = admin_app(accounts, workers, SimpleNamespace(database=accounts.database,send=False))
    routes = {(r.method,r.resource.canonical):r.handler for r in app.router.routes()}
    guard = app.middlewares[0]
    get = SimpleNamespace(host='localhost:8081',headers={},method='GET')
    html = immediate(guard(get,routes['GET','/'])).text
    csrf = re.search("const csrf='([a-f0-9]+)'", html).group(1)
    request = SimpleNamespace(host='localhost:8081',headers={'X-Admin-CSRF':csrf,'Origin':'http://localhost:8081'},
        method='POST',content_type='application/json',json=AsyncMock(return_value=account_values()))
    response = immediate(guard(request,routes['POST','/api/users']))
    assert response.status == 201
    data = json.loads(response.text)
    user_id = data['user']['id']
    assert 'private-pass' not in response.text and 'cpass' not in response.text and 'username' not in response.text
    request.match_info={'user_id':user_id}
    request.method='PUT';request.json=AsyncMock(return_value={'enabled':True})
    assert immediate(guard(request,routes['PUT','/api/users/{user_id}'])).status == 200
    assert accounts.get(user_id)['enabled']
    request.method='DELETE';request.json=AsyncMock(return_value={'confirm':'wrong'})
    assert immediate(guard(request,routes['DELETE','/api/users/{user_id}'])).status == 400
    assert accounts.get(user_id)
    request.json=AsyncMock(return_value={'confirm':user_id})
    assert immediate(guard(request,routes['DELETE','/api/users/{user_id}'])).status == 200
    assert not accounts.get(user_id)
    accounts.close()


def test_failed_worker_backoff_even_when_finally_sets_stop(tmp_path):
    accounts, _ = registry(tmp_path)
    user = accounts.save(dict(account_values(), enabled=True))
    args = SimpleNamespace(database=accounts.database,send=False)
    workers = Workers(args,accounts)
    workers.running[user['id']] = {'revision':user['revision'], 'task':SimpleNamespace(done=lambda:True),
                                  'stop':SimpleNamespace(is_set=lambda:True)}
    async def remove(user_id):
        workers.running.pop(user_id,None)
    workers.stop = remove
    immediate(workers._reconcile())
    assert user['id'] in workers.errors
    assert workers.restart_after[user['id']] > time.monotonic()
    assert user['id'] not in workers.running
    accounts.close()
