"""Human-readable status from stored state; no network probes or refreshes."""
from datetime import datetime
from .engine import BANGKOK


def status_text(engine, now):
    def stamp(value):
        return datetime.fromtimestamp(value, BANGKOK).strftime('%d %b %Y, %H:%M') if value is not None else 'Not yet'

    last = engine.store.get('last_refresh')
    if engine.store.get('refresh_failed', False):
        refresh = 'Failed; retry pending'
    elif last is None:
        refresh = 'No successful update yet'
    else:
        refresh = 'Successful'
    last_push = engine.db.execute('SELECT MAX(received) FROM push_inbox').fetchone()[0]
    outbox = dict(engine.db.execute('SELECT state,COUNT(*) FROM app_outbox GROUP BY state'))
    weekly = len(engine.homework(now))
    return '\n'.join([
        'mCV STATUS',
        'Service: responding',
        'Time zone: Bangkok (UTC+7)',
        '',
        'ASSIGNMENTS',
        'Latest update: ' + refresh,
        'Last success: ' + stamp(last),
        f'Due today through +7 days: {weekly}' if last is not None else 'Due today through +7 days: unavailable',
        '(Includes submitted work)',
        '',
        'COURSEVILLE PUSH',
        'Last received: ' + stamp(last_push),
        'Waiting to process: ' + str(engine.store.counts().get('pending', 0)),
        '',
        'LINE DELIVERY',
        'Pending: ' + str(outbox.get('pending', 0)),
        'Failed: ' + str(outbox.get('failed', 0)),
        '(Before this reply is queued)',
        '',
        'Saved state only; no live connection check.',
        '',
        'COMMANDS',
        'homework - saved assignments',
        'settings - notification preferences',
    ])
