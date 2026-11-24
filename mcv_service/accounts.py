"""Encrypted CourseVille accounts and admin metadata, separate from per-user state."""
import base64
import re
import sqlite3
import time
import uuid
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class Accounts:
    def __init__(self, database, key_path, primary_user='u1'):
        self.database = Path(database).resolve()
        self.primary_user = primary_user
        self.key_path = Path(key_path)
        self.db = sqlite3.connect(self.database, timeout=10)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS user(user_id TEXT PRIMARY KEY,cname TEXT,cpass TEXT,Line_uid TEXT);
            CREATE TABLE IF NOT EXISTS admin_users(
                user_id TEXT PRIMARY KEY,label TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,
                deleted INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS admin_invites(
                token_hash TEXT PRIMARY KEY,event_id TEXT UNIQUE NOT NULL,line_id TEXT NOT NULL,
                created REAL NOT NULL,expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS admin_audit(
                id INTEGER PRIMARY KEY,at REAL NOT NULL,action TEXT NOT NULL,user_id TEXT NOT NULL);
        ''')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(admin_users)')}
        if 'approved' not in columns:
            self.db.execute('ALTER TABLE admin_users ADD COLUMN approved INTEGER NOT NULL DEFAULT 1')
            self.db.commit()
        with self.db:
            self.db.execute('''INSERT OR IGNORE INTO admin_users(user_id,label,enabled,created)
                SELECT user_id,user_id,CASE WHEN user_id=? THEN 1 ELSE 0 END,? FROM user''', (primary_user, time.time()))

    def list(self):
        return [dict(zip(('id', 'label', 'enabled', 'revision', 'line_id', 'approved'), row)) for row in
                self.db.execute('''SELECT a.user_id,a.label,a.enabled,a.revision,u.Line_uid,a.approved
                    FROM admin_users a JOIN user u ON u.user_id=a.user_id
                    WHERE a.deleted=0 ORDER BY a.created,a.user_id''')]

    def audit(self):
        return [dict(zip(('at', 'action', 'user_id'), row)) for row in
                self.db.execute('SELECT at,action,user_id FROM admin_audit ORDER BY id DESC LIMIT 50')]

    def get(self, user_id):
        return next((item for item in self.list() if item['id'] == user_id), None)

    def encrypt(self, value):
        key = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None).public_key()
        try:
            raw = key.encrypt(value.encode(), padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        except ValueError:
            raise ValueError('Account field is too long for the encryption key.') from None
        return base64.b64encode(raw).decode()

    def save(self, values, user_id=None, pending=False):
        allowed = {'label', 'line_id', 'username', 'password', 'enabled'}
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError('Invalid account fields.')
        previous = self.get(user_id) if user_id else None
        if user_id and previous is None:
            raise ValueError('User does not exist.')
        label = values.get('label', previous['label'] if previous else '')
        line_id = values.get('line_id', previous['line_id'] if previous else '')
        enabled = values.get('enabled', bool(previous['enabled']) if previous else True)
        username, password = values.get('username', ''), values.get('password', '')
        if not isinstance(label, str) or not label.strip() or len(label) > 100:
            raise ValueError('Display name is required (up to 100 characters).')
        if not isinstance(line_id, str) or not re.fullmatch(r'U[0-9a-fA-F]{32}', line_id):
            raise ValueError('LINE user ID must be U followed by 32 hexadecimal characters.')
        line_id = 'U' + line_id[1:].lower()
        if type(enabled) is not bool:
            raise ValueError('Enabled must be true or false.')
        if not isinstance(username, str) or not isinstance(password, str) or bool(username) != bool(password):
            raise ValueError('Provide both CourseVille username and password, or leave both blank to keep them.')
        if not previous and not username:
            raise ValueError('CourseVille credentials are required for a new user.')
        duplicate = self.db.execute('''SELECT a.user_id FROM user u JOIN admin_users a ON a.user_id=u.user_id
            WHERE u.Line_uid=? AND a.deleted=0 AND a.user_id!=?''', (line_id, user_id or '')).fetchone()
        if duplicate:
            raise ValueError('This LINE user is already assigned to another account.')
        if previous and username:
            from receiver.courseville import legacy_account
            current_username, _ = legacy_account(self.database, self.key_path, user_id)
            if username != current_username:
                raise ValueError('For a different CourseVille account, create a new user. To update a password, enter the existing username.')
        encrypted = (self.encrypt(username), self.encrypt(password)) if username else None
        user_id = user_id or 'u_' + uuid.uuid4().hex
        with self.db:
            if previous:
                self.db.execute('UPDATE user SET Line_uid=? WHERE user_id=?', (line_id, user_id))
                if encrypted:
                    self.db.execute('UPDATE user SET cname=?,cpass=? WHERE user_id=?', (*encrypted, user_id))
                self.db.execute('UPDATE admin_users SET label=?,enabled=?,approved=CASE WHEN ?=1 THEN 1 ELSE approved END,revision=revision+1 WHERE user_id=?',
                                (label.strip(), int(enabled), int(enabled), user_id))
            else:
                self.db.execute('INSERT INTO user(user_id,cname,cpass,Line_uid) VALUES(?,?,?,?)', (user_id, *encrypted, line_id))
                self.db.execute('INSERT INTO admin_users(user_id,label,enabled,created,approved) VALUES(?,?,?,?,?)',
                                (user_id, label.strip(), 0 if pending else int(enabled), time.time(), 0 if pending else 1))
            self.db.execute('INSERT INTO admin_audit(at,action,user_id) VALUES(?,?,?)',
                            (time.time(), 'user.registered_pending' if pending else 'user.updated' if previous else 'user.created', user_id))
        return self.get(user_id)

    def delete(self, user_id):
        user = self.get(user_id)
        if not user:
            raise ValueError('User does not exist.')
        with self.db:
            self.db.execute('UPDATE admin_users SET enabled=0,deleted=1,revision=revision+1 WHERE user_id=?', (user_id,))
            self.db.execute('DELETE FROM user WHERE user_id=?', (user_id,))
            self.db.execute('UPDATE admin_invites SET used=1 WHERE line_id=?', (user['line_id'],))
            self.db.execute('INSERT INTO admin_audit(at,action,user_id) VALUES(?,?,?)',
                            (time.time(), 'user.deleted', user_id))
        # Receiver identities and notification history remain isolated on disk.

    def state_path(self, runtime_database, user_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', user_id):
            raise ValueError('Unsafe account ID.')
        primary = Path(runtime_database).resolve()
        return primary if user_id == self.primary_user else primary.parent / 'users' / (user_id + '.db')

    def close(self):
        self.db.close()
