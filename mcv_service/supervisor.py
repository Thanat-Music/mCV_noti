"""Multi-account worker lifecycle and one public LINE callback."""
import asyncio
import base64
import copy
import hashlib
import hmac
import json
import signal
import time
from aiohttp import web
from dotenv import dotenv_values
from receiver.store import ReceiverLock
from receiver.logging import event
from .accounts import Accounts
from .webhook import application


class Workers:
    def __init__(self, args, accounts):
        self.args, self.accounts = args, accounts
        self.lock = asyncio.Lock()
        self.running = {}
        self.errors = {}
        self.restart_after = {}

    async def stop(self, user_id):
        entry = self.running.pop(user_id, None)
        if entry:
            entry['stop'].set()
            try:
                await asyncio.wait_for(asyncio.shield(entry['task']), timeout=45)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                entry['task'].cancel()
                await asyncio.gather(entry['task'], return_exceptions=True)
            except Exception:
                pass

    async def reconcile(self):
        async with self.lock:
            await self._reconcile()

    async def _reconcile(self):
        users = {item['id']: item for item in self.accounts.list() if item['enabled']}
        for user_id, entry in list(self.running.items()):
            if user_id not in users or users[user_id]['revision'] != entry['revision'] or entry['task'].done():
                failed = entry['task'].done() and user_id in users and users[user_id]['revision'] == entry['revision']
                if failed:
                    self.errors[user_id] = 'Worker stopped unexpectedly; retrying.'
                    self.restart_after[user_id] = time.monotonic()+30
                await self.stop(user_id)
        for user_id, user in users.items():
            if user_id in self.running or time.monotonic() < self.restart_after.get(user_id, 0):
                continue
            from .__main__ import daemon
            args = copy.copy(self.args)
            args.database = self.accounts.state_path(self.args.database, user_id)
            args.legacy_user = user_id
            args.webhook = False
            args.seconds = 0
            args.once = False
            entry = {'revision': user['revision'], 'stop': asyncio.Event(), 'engine': None,
                     'recipient': user['line_id'], 'app': None}
            def ready(engine, recipient, entry=entry, user_id=user_id):
                entry['engine'], entry['recipient'] = engine, recipient
                entry['app'] = application(engine, self.secret, recipient, '/settings/' + user_id)
                self.errors.pop(user_id, None)
            entry['task'] = asyncio.create_task(daemon(args, entry['stop'], ready))
            self.running[user_id] = entry

    def public_app(self, secret):
        self.secret = secret
        from .enrollment import Enrollment
        self.enrollment = Enrollment(self.accounts, secret)
        app = web.Application(client_max_size=65536)

        async def callback(request):
            body = await request.read()
            signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest())
            if not hmac.compare_digest(signature, request.headers.get('X-Line-Signature', '').encode()):
                raise web.HTTPBadRequest()
            try:
                events = json.loads(body)['events']
                if not isinstance(events, list) or any(not isinstance(item, dict) for item in events):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise web.HTTPBadRequest() from None
            registered = {user['line_id']: user for user in self.accounts.list()}
            for item in events:
                source, message = item.get('source', {}), item.get('message', {})
                if not isinstance(source, dict) or not isinstance(message, dict):
                    continue
                recipient = source.get('userId')
                event_id = item.get('webhookEventId')
                command = message.get('text', '')
                if (item.get('type') != 'message' or message.get('type') != 'text'
                        or not isinstance(command, str) or command.strip().lower() != 'start'
                        or not isinstance(event_id, str) or not isinstance(recipient, str)):
                    continue
                user = registered.get(recipient)
                if user and user['enabled']:
                    continue
                if user:
                    text = 'Registration received. Waiting for admin approval.' if not user['approved'] else 'Your account is paused. Contact dev to resume notifications.'
                else:
                    try:
                        token = self.enrollment.invite(recipient, event_id)
                    except ValueError as exc:
                        text = str(exc)
                    else:
                        text = 'Join mCV Notifier\n\nOpen this private link to enter your CourseVille account:\n' + str(request.url.origin().with_scheme('https')) + '/register?token=' + token + '\n\nYour LINE account is linked automatically. Link expires in 15 minutes. Admin approval is required.'
                self.enrollment.queue(recipient, event_id, text)
            source_users = {item.get('source', {}).get('userId') for item in events if isinstance(item.get('source', {}), dict)}
            unavailable = False
            for user in self.accounts.list():
                if not user['enabled'] or user['line_id'] not in source_users:
                    continue
                entry = self.running.get(user['id'])
                if not entry or not entry['app'] or entry['task'].done():
                    unavailable = True
                    continue
                handler = next(route.handler for route in entry['app'].router.routes()
                               if route.method == 'POST' and route.resource.canonical == '/callback')
                await handler(request)
            if unavailable:
                # Ready users were deduplicated; let LINE retry for workers still starting.
                raise web.HTTPServiceUnavailable()
            return web.Response(text='OK')

        async def settings(request):
            entry = self.running.get(request.match_info['user_id'])
            if not entry or not entry['app'] or entry['task'].done():
                raise web.HTTPNotFound(text='Account is paused or unavailable.')
            handler = next(route.handler for route in entry['app'].router.routes()
                           if route.method == request.method and route.resource.canonical.startswith('/settings/'))
            return await handler(request)

        async def health(request):
            return web.json_response({'ready': True})
        app.router.add_get('/register', self.enrollment.page)
        app.router.add_post('/register', self.enrollment.page)
        app.router.add_get('/healthz', health)
        app.router.add_post('/callback', callback)
        app.router.add_get('/settings/{user_id}', settings)
        app.router.add_post('/settings/{user_id}', settings)
        return app


async def serve(args):
    import os
    from .admin import application as admin_application
    os.umask(0o077)
    if args.once:
        raise ValueError('--once is not supported with --multi-user')
    values = dotenv_values(args.line_env)
    secret = values.get('CHANNEL_SECRET')
    if not secret or args.send and not values.get('CHANNEL_ACCESS_TOKEN'):
        raise RuntimeError('line_credentials_missing')
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
    if args.seconds:
        loop.call_later(args.seconds, stop.set)
    with ReceiverLock(str(args.database)+'.supervisor'):
        accounts = Accounts(args.legacy_database, args.legacy_key, args.legacy_user)
        workers = Workers(args, accounts)
        runners = []
        signup_task = None
        try:
            public = workers.public_app(secret)
            signup_task = asyncio.create_task(workers.enrollment.deliver(stop, values.get('CHANNEL_ACCESS_TOKEN'), args.send))
            apps = [(public, args.port)] if args.webhook else []
            apps.append((admin_application(accounts, workers, args), args.admin_port))
            for app, port in apps:
                runner = web.AppRunner(app, access_log=None)
                runners.append(runner)
                await runner.setup()
                await web.TCPSite(runner, '127.0.0.1', port).start()
            event('admin.started')
            while not stop.is_set():
                if signup_task.done():
                    if not signup_task.cancelled():
                        signup_task.exception()  # Retrieve without logging request/credential data.
                    event('admin.signup_delivery_restarted')
                    signup_task = asyncio.create_task(workers.enrollment.deliver(stop, values.get('CHANNEL_ACCESS_TOKEN'), args.send))
                await workers.reconcile()
                try:
                    await asyncio.wait_for(stop.wait(), timeout=2)
                except asyncio.TimeoutError:
                    pass
        finally:
            stop.set()
            if signup_task:
                try:
                    await asyncio.wait_for(signup_task, timeout=35)
                except asyncio.TimeoutError:
                    signup_task.cancel()
                    await asyncio.gather(signup_task, return_exceptions=True)
            for runner in reversed(runners):
                await runner.cleanup()
            await asyncio.gather(*(workers.stop(key) for key in list(workers.running)))
            accounts.close()
