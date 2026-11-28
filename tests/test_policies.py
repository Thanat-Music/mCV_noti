"""Policy acknowledgment checks using only SQLite and the standard library."""
import sqlite3
import unittest
from html.parser import HTMLParser

from mcv_service.enrollment import Enrollment, signup_html
from mcv_service.policies import POLICY_VERSION, CONTACT, OPERATOR, PASSWORD_NOTICE, policy_html


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'input':
            self.inputs.append(dict(attrs))


class FakeAccounts:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('''CREATE TABLE admin_invites(token_hash TEXT PRIMARY KEY,
            event_id TEXT UNIQUE,line_id TEXT,created REAL,expires REAL,used INTEGER)''')
        self.users = []

    def list(self):
        return self.users

    def save(self, values, pending=False):
        self.users.append({'id': 'test-user', 'line_id': values['line_id']})
        return self.users[-1]


class PolicyTests(unittest.TestCase):
    def test_missing_or_old_acknowledgment_cannot_create_account(self):
        accounts = FakeAccounts()
        self.addCleanup(accounts.db.close)
        enrollment = Enrollment(accounts, 'test-secret')
        token = enrollment.invite('test-recipient', 'event')
        for options in ({}, {'terms_accepted': True},
                        {'terms_accepted': True, 'privacy_acknowledged': True, 'policy_version': 'old'}):
            with self.assertRaises(ValueError):
                enrollment.register(token, 'Test', 'student', 'test-password', **options)
            self.assertEqual(accounts.users, [])
            self.assertEqual(enrollment.valid(token), 'test-recipient')
        result = enrollment.register(token, 'Test', 'student', 'test-password',
            terms_accepted=True, privacy_acknowledged=True, policy_version=POLICY_VERSION)
        record = accounts.db.execute('SELECT * FROM admin_policy_acceptance').fetchone()
        self.assertEqual(record[:3], (result['id'], POLICY_VERSION, POLICY_VERSION))
        self.assertGreater(record[3], 0)
        self.assertIsNone(enrollment.valid(token))
        with self.assertRaises(ValueError):
            enrollment.register(token, 'Test', 'student', 'test-password',
                terms_accepted=True, privacy_acknowledged=True, policy_version=POLICY_VERSION)

    def test_form_requires_two_unchecked_boxes_and_escapes_errors(self):
        page = signup_html('test-token', '<script>alert(1)</script>')
        parser = FormParser()
        parser.feed(page)
        boxes = [item for item in parser.inputs if item.get('type') == 'checkbox']
        self.assertEqual({item['name'] for item in boxes}, {'terms_accepted', 'privacy_acknowledged'})
        for box in boxes:
            self.assertIn('required', box)
            self.assertNotIn('checked', box)
        self.assertNotIn('<script>', page)
        self.assertIn('href="/terms"', page)
        self.assertIn('href="/privacy"', page)
        self.assertIn(CONTACT, page)
        self.assertIn(PASSWORD_NOTICE, page)

    def test_public_notices_include_operator_and_version(self):
        for kind in ('terms', 'privacy'):
            page = policy_html(kind)
            self.assertIn(OPERATOR, page)
            self.assertIn(CONTACT, page)
            self.assertIn(POLICY_VERSION, page)
            self.assertIn(PASSWORD_NOTICE, page)
            self.assertNotIn('{PASSWORD_NOTICE}', page)
            self.assertNotIn('test-token', page)
        self.assertIn('Cloudflare', policy_html('privacy'))
        self.assertIn(PASSWORD_NOTICE, policy_html('privacy'))
        with self.assertRaises(ValueError):
            policy_html('unknown')


if __name__ == '__main__':
    unittest.main()
