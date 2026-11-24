"""SSH-only admin server. Bind only to 127.0.0.1 on a separate port."""
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path
from aiohttp import web
from .dashboard import read_snapshot
from .engine import NOTIFICATION_TYPES


def application(accounts, workers, args):
    csrf = secrets.token_hex(32)
    allowed_hosts = {'127.0.0.1', 'localhost', '[::1]'}

    @web.middleware
    async def guard(request, handler):
        hostname = request.host.rsplit(':', 1)[0] if ':' in request.host else request.host
        if hostname not in allowed_hosts or request.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise web.HTTPForbidden()
        if request.method not in ('GET', 'HEAD'):
            if not hmac.compare_digest(request.headers.get('X-Admin-CSRF', ''), csrf):
                raise web.HTTPForbidden()
            origin = request.headers.get('Origin')
            if origin and origin != 'http://' + request.host:
                raise web.HTTPForbidden()
        try:
            response = await handler(request)
        except ValueError as exc:
            response = web.json_response({'error': str(exc)}, status=400)
        except sqlite3.Error:
            response = web.json_response({'error': 'Database is busy or unavailable. Try again.'}, status=503)
        response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
            'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'none'; frame-ancestors 'none'; form-action 'self'"})
        return response

    app = web.Application(client_max_size=16384, middlewares=[guard])

    def require_user(user_id):
        user = accounts.get(user_id)
        if not user:
            raise web.HTTPNotFound()
        return user

    async def body(request):
        if request.content_type != 'application/json':
            raise web.HTTPUnsupportedMediaType()
        try:
            value = await request.json()
        except (ValueError, UnicodeError):
            raise web.HTTPBadRequest() from None
        if not isinstance(value, dict):
            raise web.HTTPBadRequest()
        return value

    def user_view(user):
        entry = workers.running.get(user['id'])
        running = bool(entry and entry['engine'] and not entry['task'].done())
        result = {**user, 'enabled': bool(user['enabled']), 'worker': 'running' if running else 'awaiting approval' if not user['approved'] else 'paused' if not user['enabled'] else 'starting',
                  'worker_error': workers.errors.get(user['id'])}
        snapshot = read_snapshot(accounts.state_path(args.database, user['id']))
        result['summary'] = {key: snapshot.get(key) for key in ('available', 'last_refresh', 'refresh_failed', 'weekly', 'last_push', 'outbox')}
        return result

    async def index(request):
        html = Path(__file__).with_name('admin.html').read_text(encoding='utf-8').replace('__CSRF__', csrf)
        return web.Response(text=html, content_type='text/html')

    async def overview(request):
        return web.json_response({'users': [user_view(user) for user in accounts.list()],
                                  'audit': accounts.audit(), 'send_enabled': args.send, 'at': time.time()})

    async def details(request):
        user = require_user(request.match_info['user_id'])
        result = read_snapshot(accounts.state_path(args.database, user['id']))
        return web.json_response({'user': user_view(user), 'snapshot': result})

    async def create(request):
        result = accounts.save(await body(request))
        await workers.reconcile()
        return web.json_response({'user': user_view(result)}, status=201)

    async def update(request):
        user_id = request.match_info['user_id']
        require_user(user_id)
        values = await body(request)
        try:
            async with workers.lock:
                await workers.stop(user_id)
                result = accounts.save(values, user_id)
        finally:
            await workers.reconcile()
        return web.json_response({'user': user_view(result)})

    async def delete(request):
        user_id = request.match_info['user_id']
        require_user(user_id)
        if (await body(request)).get('confirm') != user_id:
            raise ValueError('Confirm the exact user ID to delete the account.')
        async with workers.lock:
            await workers.stop(user_id)
            accounts.delete(user_id)
        return web.json_response({'deleted': True})

    async def preferences(request):
        user_id = request.match_info['user_id']
        require_user(user_id)
        values = await body(request)
        if set(values) != set(NOTIFICATION_TYPES) or any(type(v) is not bool for v in values.values()):
            raise ValueError('Invalid notification preferences.')
        path = accounts.state_path(args.database, user_id)
        if not path.exists():
            raise ValueError('Wait until this account has started once before configuring notifications.')
        db = sqlite3.connect(path, timeout=5)
        try:
            with db:
                db.execute('INSERT INTO push_state VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',
                           ('notification_preferences', json.dumps(values)))
        finally:
            db.close()
        with accounts.db:
            accounts.db.execute('INSERT INTO admin_audit(at,action,user_id) VALUES(?,?,?)',
                                (time.time(), 'preferences.updated', user_id))
        return web.json_response({'saved': True})

    async def refresh(request):
        user_id = request.match_info['user_id']
        require_user(user_id)
        entry = workers.running.get(user_id)
        if not entry or not entry['engine'] or entry['task'].done():
            raise ValueError('Enable the account and wait for its worker to start first.')
        with entry['engine'].db:
            entry['engine'].db.execute('UPDATE push_refresh SET requested=requested+1 WHERE singleton=1')
        with accounts.db:
            accounts.db.execute('INSERT INTO admin_audit(at,action,user_id) VALUES(?,?,?)',
                                (time.time(), 'refresh.requested', user_id))
        return web.json_response({'queued': True})

    app.router.add_get('/', index)
    app.router.add_get('/api/overview', overview)
    app.router.add_post('/api/users', create)
    app.router.add_get('/api/users/{user_id}', details)
    app.router.add_put('/api/users/{user_id}', update)
    app.router.add_delete('/api/users/{user_id}', delete)
    app.router.add_put('/api/users/{user_id}/preferences', preferences)
    app.router.add_post('/api/users/{user_id}/refresh', refresh)
    return app
