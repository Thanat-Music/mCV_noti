"""Transactional snapshots, reminder generations, and a durable LINE outbox."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from .push_types import PUSH_TYPES, classify_push

BANGKOK = timezone(timedelta(hours=7))
DAY = 86400
NOTIFICATION_TYPES = {
    "initial_summary": "Initial assignment summary",
    "new_assignment": "New assignments",
    "deadline_changed": "Changed deadlines",
    "deadline_summary": "Daily deadline reminders (3 days / 1 day)",
    **PUSH_TYPES,
    "incident": "Refresh failures",
    "recovery": "Refresh recovery",
}


def due_timestamp(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("deadline_timezone_missing")
    return parsed.timestamp()


def normalize(courses):
    result = {}
    for course in courses:
        for assignment in course["assignments"]:
            key = str(course["courseID"]) + ":" + str(assignment["id"])
            if key in result:
                raise ValueError("duplicate_assignment_id")
            result[key] = {"id": key, "title": str(assignment["title"]),
                "course": str(course["title"]), "status": str(assignment["status"]),
                "due": due_timestamp(assignment.get("dueDate"))}
    return result


class Engine:
    def __init__(self, store):
        self.store, self.db = store, store.db
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS app_items (
                id TEXT PRIMARY KEY, data TEXT NOT NULL, generation INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS app_reminders (
                item TEXT NOT NULL, generation INTEGER NOT NULL, days INTEGER NOT NULL,
                fire_at REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                PRIMARY KEY(item,generation,days));
            CREATE TABLE IF NOT EXISTS app_outbox (
                id TEXT PRIMARY KEY, dedupe TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
                refs TEXT NOT NULL, text TEXT, retry_key TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                next_try REAL NOT NULL DEFAULT 0, created REAL NOT NULL, expires REAL);
        ''')

    def preferences(self):
        saved = self.store.get("notification_preferences", {})
        return {key: saved.get(key, saved.get("courseville_push", True) if key in PUSH_TYPES else True)
                for key in NOTIFICATION_TYPES}

    def save_preferences(self, values):
        if set(values) != set(NOTIFICATION_TYPES) or any(type(v) is not bool for v in values.values()):
            raise ValueError("invalid_notification_preferences")
        self.store.put("notification_preferences", values)

    def homework(self, now):
        local = datetime.fromtimestamp(now, BANGKOK)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        end = start + 8 * DAY
        items = []
        for data, generation in self.db.execute("SELECT data,generation FROM app_items WHERE active=1"):
            item = json.loads(data)
            if item["due"] is not None and start <= item["due"] < end:
                items.append(dict(item, generation=generation))
        return items

    def queue_homework(self, event_id, now):
        # Read the latest stored snapshot; this command never requests a network refresh.
        self._queue("line:" + event_id, "homework", [], now, expires=now+3600)

    def forward_pushes(self, now):
        with self.db:
            for channel, version, raw in self.db.execute(
                    "SELECT channel,version,payload FROM push_inbox WHERE state='pending'").fetchall():
                payload = json.loads(raw)
                notification = payload.get("notification")
                content = notification if isinstance(notification, dict) else payload
                parts = [content.get("title"), content.get("body"), content.get("message")]
                text = "CourseVille notification\n" + "\n".join(v[:4000] for v in parts if isinstance(v, str) and v)
                if text == "CourseVille notification\n":
                    text += "A course update was received. Open CourseVille for details."
                kind = classify_push(payload)
                self._queue("push:" + channel + ":" + version, kind, [], now, text=text)

    def _meta(self, name, value):
        # Caller owns transaction; do not use Store.put (which commits separately).
        self.db.execute("INSERT INTO push_state VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                        (name, json.dumps(value)))

    def _queue(self, dedupe, kind, refs, now, expires=None, text=None):
        self.db.execute("INSERT OR IGNORE INTO app_outbox(id,dedupe,kind,refs,text,retry_key,created,expires) VALUES(?,?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), dedupe, kind, json.dumps(refs), text, str(uuid.uuid4()), now, expires))

    @staticmethod
    def eligible(item, now):
        return item["status"] == "ASSIGNED" and (item["due"] is None or item["due"] > now)

    def snapshot(self, courses, now, refresh_generation=0):
        items = normalize(courses)  # Validate entire response before changing any state.
        baseline = self.store.get("baseline_at") is None
        old = {key: (json.loads(data), gen, active) for key, data, gen, active in
               self.db.execute("SELECT id,data,generation,active FROM app_items")}
        initial = []
        with self.db:
            self.db.execute("UPDATE app_items SET active=0")
            for key, item in items.items():
                previous = old.get(key)
                changed = previous is not None and previous[0]["due"] != item["due"]
                generation = (previous[1] + int(changed)) if previous else 1
                self.db.execute("INSERT INTO app_items VALUES(?,?,?,1) ON CONFLICT(id) DO UPDATE SET data=excluded.data,generation=excluded.generation,active=1",
                                (key, json.dumps(item), generation))
                ref = {"id": key, "generation": generation}
                if not previous or changed:
                    self.db.execute("UPDATE app_reminders SET state='cancelled' WHERE item=? AND state IN ('pending','queued')", (key,))
                    if item["due"] is not None:
                        for days in (3, 1):
                            fire = item["due"] - days * DAY
                            if fire > now:
                                self.db.execute("INSERT INTO app_reminders(item,generation,days,fire_at) VALUES(?,?,?,?)",
                                                (key, generation, days, fire))
                    if not baseline and self.eligible(item, now):
                        self._queue(f"item:{key}:{generation}", "deadline_changed" if previous else "new_assignment", [ref], now)
                if baseline and self.eligible(item, now):
                    initial.append(ref)
            # Removed items and newly submitted work cannot retain pending reminders.
            for key, (previous, gen, _) in old.items():
                if key not in items or not self.eligible(items[key], now):
                    self.db.execute("UPDATE app_reminders SET state='cancelled' WHERE item=? AND state IN ('pending','queued')", (key,))
            if baseline:
                self._queue("initial", "initial_summary", initial, now,
                            text="Initial summary: no open assignments." if not initial else None)
                self._meta("baseline_at", now)
            self._meta("last_refresh", now)
            self.db.execute("UPDATE push_refresh SET completed=MAX(completed,?) WHERE singleton=1", (refresh_generation,))
            self.db.execute("UPDATE push_inbox SET state='processed' WHERE state='pending' AND received<=?", (now,))

    def morning(self, now):
        local = datetime.fromtimestamp(now, BANGKOK)
        at_six = local.replace(hour=6, minute=0, second=0, microsecond=0).timestamp()
        if now < at_six or self.store.get("baseline_at") is None:
            return
        day = local.date().isoformat()
        refs = []
        with self.db:
            # Missed earlier days aren't replayed. Today's catch-up can include thresholds
            # reached since yesterday's normal summary, provided their deadline is future.
            self.db.execute("UPDATE app_reminders SET state='skipped' WHERE state='pending' AND fire_at<?", (at_six-DAY,))
            for key, generation, days in self.db.execute(
                    "SELECT item,generation,days FROM app_reminders WHERE state='pending' AND fire_at<=?", (now,)).fetchall():
                refs.append({"id": key, "generation": generation, "days": days})
            before = self.db.total_changes
            self._queue("summary:" + day, "deadline_summary", refs, now,
                        expires=(local.replace(hour=0, minute=0, second=0, microsecond=0)+timedelta(days=1)).timestamp())
            if self.db.total_changes > before:
                for ref in refs:
                    self.db.execute("UPDATE app_reminders SET state='queued' WHERE item=? AND generation=? AND days=?",
                                    (ref["id"], ref["generation"], ref["days"]))

    def prepare(self, row, now):
        """Revalidate immediately before sending; freeze content across equivalent retries."""
        out_id, kind, refs_raw, text, retry_key, attempts, expires = row
        if expires is not None and now >= expires:
            with self.db:
                self.db.execute("UPDATE app_outbox SET state='expired' WHERE id=?", (out_id,))
            return None
        # Existing unclassified outbox rows use the Other preference after upgrading.
        preference_kind = "push_other" if kind == "courseville_push" else kind
        if preference_kind in NOTIFICATION_TYPES and not self.preferences()[preference_kind]:
            with self.db:
                self.db.execute("UPDATE app_outbox SET state='cancelled' WHERE id=?", (out_id,))
            return None
        if kind == "homework" and text is None:
            from .flex import assignment_messages
            items = sorted(self.homework(now), key=lambda item: (item["due"], item["id"]))
            label = "Homework: today through 7 days ahead (Bangkok)"
            last = self.store.get("last_refresh")
            if last is None:
                messages = [{"type": "text", "text": "No assignment data saved yet. Homework will be available after the next successful scheduled or push update."}]
            else:
                updated = datetime.fromtimestamp(last, BANGKOK).strftime("%d %b %Y %H:%M Bangkok")
                messages = [{"type": "text", "text": "Homework from saved data. Last update: " + updated}]
                messages.extend(assignment_messages(items, label, now))
            text = json.dumps(messages)
            with self.db:
                self.db.execute("UPDATE app_outbox SET text=? WHERE id=?", (text, out_id))
            return out_id, text, retry_key
        if kind == "homework":
            return out_id, text, retry_key
        original = json.loads(refs_raw)
        refs, items = [], {}
        for ref in original:
            item_row = self.db.execute("SELECT data,generation,active FROM app_items WHERE id=?", (ref["id"],)).fetchone()
            if not item_row:
                continue
            item = json.loads(item_row[0])
            if item_row[2] and item_row[1] == ref["generation"] and self.eligible(item, now):
                refs.append(ref)
                items[ref["id"]] = item
        if not refs and (original or text is None):
            with self.db:
                self.db.execute("UPDATE app_outbox SET state='cancelled' WHERE id=?", (out_id,))
            return None
        if text is None or refs != original:
            label = {"deadline_summary": "Deadline reminders", "initial_summary": "Initial assignments",
                     "new_assignment": "New assignment", "deadline_changed": "Deadline changed"}.get(kind, kind)
            lines = [label]
            for item in items.values():
                due = datetime.fromtimestamp(item["due"], BANGKOK).strftime("%d %b %H:%M") if item["due"] else "No deadline"
                lines.append(f"{item['course']}: {item['title']} — {due}")
            if kind == "deadline_summary" and self.store.get("refresh_failed", False):
                last = self.store.get("last_refresh")
                lines.append("Based on last successful update: " + datetime.fromtimestamp(last, BANGKOK).strftime("%d %b %H:%M"))
            text = "\n".join(lines)
            # Changed content must use a new LINE retry key. Rare duplicates are preferred
            # to retrying expired work or dropping still-eligible items after a partial change.
            if refs != original:
                retry_key = str(uuid.uuid4())
            with self.db:
                self.db.execute("UPDATE app_outbox SET refs=?,text=?,retry_key=? WHERE id=?",
                                (json.dumps(refs), text, retry_key, out_id))
        return out_id, text, retry_key

    def delivery_messages(self, out_id, text, now):
        row = self.db.execute("SELECT kind,refs FROM app_outbox WHERE id=?", (out_id,)).fetchone()
        if row[0] == "homework":
            return json.loads(text)
        from .flex import assignment_messages
        refs = json.loads(row[1])
        if not refs:
            return [{"type": "text", "text": text[i:i+2000]} for i in range(0, len(text), 2000)]
        cache_key = "flex:" + out_id
        cached = self.store.get(cache_key)
        if cached and cached["text"] == text:
            return cached["messages"]
        items = [json.loads(self.db.execute("SELECT data FROM app_items WHERE id=?", (ref["id"],)).fetchone()[0]) for ref in refs]
        messages = assignment_messages(items, text.split("\n")[0], now)
        if "last successful update" in text:
            messages.insert(0, {"type": "text", "text": text.split("\n")[-1]})
        self.store.put(cache_key, {"text": text, "messages": messages})
        return messages

    def pending(self, now):
        return self.db.execute("SELECT id,kind,refs,text,retry_key,attempts,expires FROM app_outbox WHERE state='pending' AND next_try<=? ORDER BY created LIMIT 20", (now,)).fetchall()

    def accepted(self, out_id):
        with self.db:
            refs = json.loads(self.db.execute("SELECT refs FROM app_outbox WHERE id=?", (out_id,)).fetchone()[0])
            self.db.execute("UPDATE app_outbox SET state='sent' WHERE id=?", (out_id,))
            for ref in refs:
                if "days" in ref:
                    self.db.execute("UPDATE app_reminders SET state='sent' WHERE item=? AND generation=? AND days=?",
                                    (ref["id"], ref["generation"], ref["days"]))

    def failed(self, out_id, now, permanent=False):
        with self.db:
            attempts = self.db.execute("SELECT attempts FROM app_outbox WHERE id=?", (out_id,)).fetchone()[0] + 1
            self.db.execute("UPDATE app_outbox SET attempts=?,next_try=?,state=? WHERE id=?",
                            (attempts, now + min(3600, 30 * 2 ** min(attempts, 7)), "failed" if permanent else "pending", out_id))

    def incident(self, active, now):
        old = self.store.get("refresh_incident", False)
        if active == old:
            return
        with self.db:
            self._meta("refresh_incident", active)
            if not active:
                self.db.execute("UPDATE app_outbox SET state='cancelled' WHERE kind='incident' AND state='pending'")
            self._queue("incident:" + str(now), "incident" if active else "recovery", [], now,
                        text="mCV needs attention: assignment refresh is failing." if active else "mCV assignment refresh recovered.")

    def retention(self, now):
        with self.db:
            # Pending work and reminder identities survive diagnostic retention.
            self.db.execute("DELETE FROM push_inbox WHERE state='processed' AND received<?", (now-7*DAY,))
            self.db.execute("DELETE FROM push_state WHERE name LIKE 'flex:%' AND substr(name,6) IN (SELECT id FROM app_outbox WHERE state IN ('sent','cancelled','expired') AND created<?)", (now-30*DAY,))
            self.db.execute("DELETE FROM app_outbox WHERE state IN ('sent','cancelled','expired') AND created<?", (now-30*DAY,))
            self._meta("retention_at", now)
