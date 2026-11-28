"""One-time, expiring signup links bound to the sender of a signed LINE start event."""
import asyncio
import uuid
import hashlib
import hmac
import time
from html import escape
from .policies import POLICY_VERSION, CONTACT, PASSWORD_NOTICE


class Enrollment:
    def __init__(self, accounts, secret):
        self.accounts, self.secret = accounts, secret
        self.accounts.db.execute("""CREATE TABLE IF NOT EXISTS admin_signup_outbox(
            event_id TEXT PRIMARY KEY,recipient TEXT NOT NULL,text TEXT NOT NULL,retry_key TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_try REAL NOT NULL DEFAULT 0,
            created REAL NOT NULL)""")
        self.accounts.db.execute("""CREATE TABLE IF NOT EXISTS admin_policy_acceptance(
            user_id TEXT NOT NULL, terms_version TEXT NOT NULL, privacy_version TEXT NOT NULL,
            accepted_at REAL NOT NULL, PRIMARY KEY(user_id,terms_version,privacy_version))""")
        self.accounts.db.commit()

    def queue(self, recipient, event_id, text):
        with self.accounts.db:
            self.accounts.db.execute("""INSERT OR IGNORE INTO admin_signup_outbox(event_id,recipient,text,retry_key,created)
                VALUES(?,?,?,?,?)""", (event_id, recipient, text, str(uuid.uuid4()), time.time()))

    async def deliver(self, stop, token, send):
        from .line import Line, DeliveryError
        while not stop.is_set():
            now = time.time()
            with self.accounts.db:
                self.accounts.db.execute("DELETE FROM admin_signup_outbox WHERE created<? AND state!='pending'", (now-7*86400,))
                self.accounts.db.execute("UPDATE admin_signup_outbox SET state='expired' WHERE state='pending' AND created<?", (now-900,))
            rows = self.accounts.db.execute("SELECT event_id,recipient,text,retry_key,attempts FROM admin_signup_outbox WHERE state='pending' AND next_try<=? ORDER BY created LIMIT 10", (now,)).fetchall() if send else []
            for event_id, recipient, text, retry_key, attempts in rows:
                if stop.is_set():
                    break
                try:
                    await asyncio.to_thread(Line(token, recipient).send, text, retry_key)
                except Exception as exc:
                    permanent = isinstance(exc, DeliveryError) and exc.permanent
                    with self.accounts.db:
                        self.accounts.db.execute("UPDATE admin_signup_outbox SET state=?,attempts=attempts+1,next_try=? WHERE event_id=?",
                            ('failed' if permanent else 'pending', time.time()+min(300, 30*2**min(attempts,4)), event_id))
                else:
                    with self.accounts.db:
                        self.accounts.db.execute("UPDATE admin_signup_outbox SET state='sent' WHERE event_id=?", (event_id,))
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    def invite(self, recipient, event_id, now=None):
        now = time.time() if now is None else now
        token = hmac.new(self.secret.encode(), ('signup:' + event_id + ':' + recipient).encode(), hashlib.sha256).hexdigest()
        hashed = hashlib.sha256(token.encode()).hexdigest()
        existing = self.accounts.db.execute('SELECT token_hash FROM admin_invites WHERE event_id=?', (event_id,)).fetchone()
        if existing:
            return token
        with self.accounts.db:
            self.accounts.db.execute('DELETE FROM admin_invites WHERE expires<?', (now-86400,))
            count = self.accounts.db.execute('SELECT COUNT(*) FROM admin_invites WHERE line_id=? AND created>?',
                                             (recipient, now-60)).fetchone()[0]
            if count >= 3:
                raise ValueError('Too many signup requests. Wait one minute.')
            self.accounts.db.execute('UPDATE admin_invites SET used=1 WHERE line_id=?', (recipient,))
            self.accounts.db.execute('INSERT INTO admin_invites VALUES(?,?,?,?,?,0)',
                                     (hashed, event_id, recipient, now, now+900))
        return token

    def valid(self, token, now=None):
        now = time.time() if now is None else now
        if not isinstance(token, str) or len(token) != 64:
            return None
        row = self.accounts.db.execute('SELECT line_id,expires,used FROM admin_invites WHERE token_hash=?',
                                       (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        return row[0] if row and row[1] > now and not row[2] else None

    def register(self, token, label, username, password, *, terms_accepted=False,
                 privacy_acknowledged=False, policy_version=None):
        recipient = self.valid(token)
        if not recipient:
            raise ValueError('This signup link expired or was used. Send start to the LINE bot for a new link.')
        if terms_accepted is not True or privacy_acknowledged is not True:
            raise ValueError('Please accept the Terms of Use and acknowledge the Privacy Notice before registering.')
        if policy_version != POLICY_VERSION:
            raise ValueError('The terms or privacy notice changed. Reload this page and read the current version.')
        if any(user['line_id'] == recipient for user in self.accounts.list()):
            raise ValueError('This LINE account is already registered. Contact dev to change its CourseVille account.')
        result = self.accounts.save({'label': label, 'username': username, 'password': password,
                                     'line_id': recipient, 'enabled': False}, pending=True)
        with self.accounts.db:
            self.accounts.db.execute('INSERT INTO admin_policy_acceptance VALUES(?,?,?,?)',
                (result['id'], POLICY_VERSION, POLICY_VERSION, time.time()))
            self.accounts.db.execute('UPDATE admin_invites SET used=1 WHERE token_hash=?',
                                     (hashlib.sha256(token.encode()).hexdigest(),))
        return result

    async def page(self, request):
        from aiohttp import web
        headers = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff',
                   'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"}
        token = request.query.get('token', '')
        error = ''
        if request.method == 'POST':
            form = await request.post()
            token = str(form.get('token', ''))
            try:
                self.register(token, form.get('label', ''), form.get('username', ''), form.get('password', ''),
                    terms_accepted=form.get('terms_accepted') == 'yes',
                    privacy_acknowledged=form.get('privacy_acknowledged') == 'yes',
                    policy_version=form.get('policy_version'))
            except ValueError as exc:
                error = str(exc)
            else:
                return web.Response(text='Registration received. Your LINE account is linked automatically. Wait for admin approval before using homework or settings.',
                                    headers=headers, content_type='text/plain')
        if not self.valid(token):
            return web.Response(status=403, text='Signup link expired or already used. Send start to the LINE bot for a new link.', headers=headers)
        return web.Response(text=signup_html(token, error), content_type='text/html', headers=headers, status=400 if error else 200)


def signup_html(token, error=''):
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Join mCV</title><style>body{font:16px system-ui;max-width:440px;margin:8vh auto;padding:24px;background:#f4f6fa;color:#152139}label{display:block;margin:18px 0}input{display:block;box-sizing:border-box;width:100%;padding:12px;margin-top:7px;border:1px solid #bbc5d5;border-radius:8px}input[type=checkbox]{display:inline-block;width:auto;margin:0 8px 0 0;vertical-align:middle}button{background:#4d0000;color:white;padding:14px 22px;border:0;border-radius:9px}.error{color:#b3261e}.notice{padding:16px;border:1px solid #d7bd9b;background:#fff4e5;border-radius:8px;line-height:1.6}a{color:#174f91}</style>
    <h1>Join mCV Notifier</h1><p>Your LINE account is linked automatically. Enter your own CourseVille account. An admin must approve registration before notifications start.</p>'''
    html += '<p class="error">' + escape(error) + '</p><form method="post" action="/register"><input type="hidden" name="token" value="' + escape(token, quote=True) + '">'
    html += '''<label>Name or nickname<input name="label" maxlength="100" required autocomplete="nickname" placeholder="e.g. Music" aria-describedby="name-help"></label>
    <p id="name-help">Choose any name so the admin can recognize you. It does not need to match your LINE name or CourseVille username.</p>
    <label>CourseVille username<input name="username" required autocomplete="username" maxlength="100"></label>
    <label>CourseVille password<input name="password" type="password" required autocomplete="current-password" maxlength="150"></label>
    '''
    html += '<input type="hidden" name="policy_version" value="' + POLICY_VERSION + '">'
    html += '''<section class="notice" lang="th"><strong>โปรดอ่านก่อนสมัคร</strong>
    <p>บริการส่วนบุคคลที่ทำเพื่อใช้เองเป็นหลัก ไม่ใช่บริการทางการของ CourseVille หรือมหาวิทยาลัย อาจแจ้งเตือนช้า ตกหล่น หรือหยุดทำงาน ต้องตรวจ CourseVille ด้วยตนเองเสมอ</p>
<p>{PASSWORD_NOTICE}</p>
    <a href="/terms" target="_blank" rel="noopener noreferrer">อ่านเงื่อนไขการใช้บริการ / Terms of Use</a><br>
    <a href="/privacy" target="_blank" rel="noopener noreferrer">อ่านประกาศความเป็นส่วนตัว / Privacy Notice</a></section>
    <label lang="th"><input type="checkbox" name="terms_accepted" value="yes" required>ฉันอ่านและยอมรับเงื่อนไขการใช้บริการ รวมถึงข้อจำกัดและความเสี่ยงที่แจ้งไว้</label>
    <label lang="th"><input type="checkbox" name="privacy_acknowledged" value="yes" required>ฉันอ่านและรับทราบประกาศความเป็นส่วนตัว ว่าจะเก็บ ใช้ และเปิดเผยข้อมูลอย่างไรเพื่อให้บริการนี้</label>
    <button>Request registration</button></form><p>Keep this signup link private; it expires in 15 minutes.</p>'''
    html += '<p>Privacy requests / ติดต่อผู้ดูแล: <a href="mailto:' + CONTACT + '">' + CONTACT + '</a></p></html>'

    return html.replace('{PASSWORD_NOTICE}', escape(PASSWORD_NOTICE))
