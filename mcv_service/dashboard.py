"""Read only selected dashboard fields; credentials and receiver keys never leave SQLite."""
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from .engine import BANGKOK, DAY, NOTIFICATION_TYPES
from .push_types import PUSH_TYPES, classify_push


def read_snapshot(database, now=None):
    path = Path(database).resolve()
    if not path.exists():
        return {'available': False, 'assignments': [], 'pushes': [], 'deliveries': [], 'preferences': {}}
    now = time.time() if now is None else now
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        db.execute('BEGIN')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'push_state', 'push_inbox', 'app_items', 'app_outbox'} <= tables:
            return {'available': False, 'assignments': [], 'pushes': [], 'deliveries': [], 'preferences': {}}
        state = {key: json.loads(raw) for key, raw in db.execute(
            "SELECT name,value FROM push_state WHERE name IN ('last_refresh','refresh_failed','notification_preferences','connected_at','verified_at')")}
        start = datetime.fromtimestamp(now, BANGKOK).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        items = []
        weekly = 0
        for (raw,) in db.execute('SELECT data FROM app_items WHERE active=1'):
            item = json.loads(raw)
            if item['due'] is not None and start <= item['due'] < start+8*DAY:
                weekly += 1
            items.append({key: item[key] for key in ('id', 'title', 'course', 'status', 'due')})
        items.sort(key=lambda item: (item['due'] is None, item['due'] or 0, item['id']))
        pushes = []
        for received, status, raw in db.execute('SELECT received,state,payload FROM push_inbox ORDER BY received DESC LIMIT 30'):
            payload = json.loads(raw)
            content = payload.get('notification') if isinstance(payload.get('notification'), dict) else payload
            pushes.append({'at': received, 'state': status, 'kind': classify_push(payload),
                           'title': str(content.get('title', 'Course update'))[:500],
                           'course': str(content.get('message', ''))[:500]})
        outbox = dict(db.execute('SELECT state,COUNT(*) FROM app_outbox GROUP BY state'))
        deliveries = [dict(zip(('kind', 'state', 'attempts', 'at'), row)) for row in db.execute(
            'SELECT kind,state,attempts,created FROM app_outbox ORDER BY created DESC LIMIT 30')]
        saved = state.get('notification_preferences', {})
        preferences = {key: saved.get(key, saved.get('courseville_push', True) if key in PUSH_TYPES else True)
                       for key in NOTIFICATION_TYPES}
        return {'available': True, 'last_refresh': state.get('last_refresh'),
                'refresh_failed': state.get('refresh_failed', False), 'last_connection': state.get('connected_at'),
                'last_push': pushes[0]['at'] if pushes else None, 'weekly': weekly, 'total_assignments': len(items),
                'assignments': items[:300], 'pushes': pushes, 'deliveries': deliveries, 'outbox': outbox,
                'preferences': preferences, 'preference_labels': NOTIFICATION_TYPES}
    finally:
        db.close()
