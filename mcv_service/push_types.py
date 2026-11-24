"""Conservative classification of CourseVille push metadata.

Exact title suffixes take priority; metadata and links are fallbacks.
Announcement is a provisional mapping pending a genuine payload sample.
"""
import re
from urllib.parse import parse_qs, urlsplit

PUSH_TYPES = {
    'push_assignment': 'CourseVille: assignments',
    'push_announcement': 'CourseVille: announcements (unverified suffix)',
    'push_material': 'CourseVille: learning materials',
    'push_score': 'CourseVille: scores',
    'push_other': 'CourseVille: other / unrecognized updates',
}
ALIASES = {
    'assignment': 'push_assignment', 'assignments': 'push_assignment',
    'homework': 'push_assignment',
    'announcement': 'push_announcement', 'announcements': 'push_announcement',
    'news': 'push_announcement',
    'material': 'push_material', 'materials': 'push_material',
    'resource': 'push_material', 'resources': 'push_material',
    'document': 'push_material', 'documents': 'push_material',
    'file': 'push_material', 'files': 'push_material',
    'score': 'push_score', 'scores': 'push_score',
}


def classify_push(payload):
    signals = set()
    containers = [payload]
    for key in ('notification', 'data'):
        if isinstance(payload.get(key), dict):
            containers.append(payload[key])
    # Observed suffixes: Assignment, Material, Score.
    # ASSUMPTION: Announcement uses the same suffix format; not yet observed.
    # Match only the final standardized label, never arbitrary words in the title.
    for container in containers:
        title = container.get('title')
        if isinstance(title, str):
            match = re.search(r' - (Assignment|Material|Announcement|Score)\s*$', title, re.IGNORECASE)
            if match:
                signals.add(ALIASES[match.group(1).lower()])
    if signals:
        return signals.pop() if len(signals) == 1 else 'push_other'
    for container in containers:
        for key in ('type', 'category', 'event', 'eventType', 'notificationType', 'contentType'):
            value = container.get(key)
            if isinstance(value, str):
                # Only explicit metadata tokens, never free-form title/body matching.
                value = re.sub(r'([a-z])([A-Z])', r'\1_\2', value)
                tokens = re.split(r'[^a-z]+', value.lower())
                signals.update(ALIASES[token] for token in tokens if token in ALIASES)
        for key in ('url', 'link', 'click_action', 'clickAction'):
            value = container.get(key)
            if not isinstance(value, str):
                continue
            try:
                url = urlsplit(value)
            except ValueError:
                continue
            if url.netloc and (url.hostname or '').lower() not in (
                    'www.mycourseville.com', 'mycourseville.com', 'alpha.mycourseville.com'):
                continue
            segments = url.path.lower().split('/')
            for query_key in ('q', 'type', 'category'):
                for query_value in parse_qs(url.query).get(query_key, []):
                    segments.extend(query_value.lower().split('/'))
            signals.update(ALIASES[segment] for segment in segments if segment in ALIASES)
    return signals.pop() if len(signals) == 1 else 'push_other'
