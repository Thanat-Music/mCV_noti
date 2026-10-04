from datetime import datetime, timedelta
import json
import pytest

from receiver.store import Store
from mcv_service.engine import Engine, BANGKOK, DAY
from mcv_service.line import Line, DeliveryError


def when(day, hour=6):
    return datetime(2026, 10, day, hour, tzinfo=BANGKOK).timestamp()


def courses(due, status="ASSIGNED", title="Homework"):
    return [{"courseID": "course-1", "title": "Control", "assignments": [{
        "id": "task-1", "title": title, "status": status,
        "dueDate": datetime.fromtimestamp(due, BANGKOK).isoformat() if due else None}]}]


@pytest.fixture
def engine(tmp_path):
    store = Store(tmp_path / "state.db")
    yield Engine(store)
    store.close()


def accept_all(engine, now):
    results = []
    for row in engine.pending(now):
        ready = engine.prepare(row, now)
        if ready:
            results.append(ready[1])
            engine.accepted(ready[0])
    return results


def test_baseline_then_once_per_threshold(engine):
    engine.snapshot(courses(when(10, 12)), when(5))
    assert len(accept_all(engine, when(5))) == 1
    engine.morning(when(7))  # 72-hour crossing is noon, not yet reached.
    assert accept_all(engine, when(7)) == []
    engine.morning(when(8))
    assert len(accept_all(engine, when(8))) == 1
    engine.morning(when(8, 12))
    assert accept_all(engine, when(8, 12)) == []
    engine.morning(when(9))
    assert accept_all(engine, when(9)) == []
    engine.morning(when(10))
    assert len(accept_all(engine, when(10))) == 1
    engine.morning(when(10, 13))
    assert accept_all(engine, when(10, 13)) == []


def test_new_assignment_late_no_catchup_threshold(engine):
    engine.snapshot([], when(5))
    accept_all(engine, when(5))
    engine.snapshot(courses(when(5, 12)), when(5, 10))
    engine.morning(when(5, 10))
    messages = accept_all(engine, when(5, 10))
    assert len(messages) == 1 and "New assignment" in messages[0]
    assert engine.db.execute("SELECT COUNT(*) FROM app_reminders").fetchone() == (0,)


def test_deadline_change_resets_generation_and_old_pending(engine):
    engine.snapshot(courses(when(10, 12)), when(5))
    accept_all(engine, when(5))
    engine.morning(when(8))
    engine.snapshot(courses(when(15, 12)), when(8, 7))
    messages = accept_all(engine, when(8, 7))
    assert len(messages) == 1 and "Deadline changed" in messages[0]
    assert engine.db.execute("SELECT generation FROM app_items").fetchone() == (2,)
    engine.morning(when(13))
    assert len(accept_all(engine, when(13))) == 1


def test_stop_at_deadline_even_cached_unsubmitted(engine):
    engine.snapshot(courses(when(10, 12)), when(5))
    accept_all(engine, when(5))
    engine.morning(when(10))
    assert accept_all(engine, when(10, 12)) == []


@pytest.mark.parametrize("status", ["SUBMITTED", "LATE_SUBMITTED", "OVERDUE"])
def test_submission_states_cancel_queued_reminders(engine, status):
    engine.snapshot(courses(when(10, 12)), when(5))
    accept_all(engine, when(5))
    engine.morning(when(8))
    engine.snapshot(courses(when(10, 12), status), when(8, 7))
    assert accept_all(engine, when(8, 7)) == []


def test_no_deadline_then_added(engine):
    engine.snapshot(courses(None), when(5))
    assert "No deadline" in accept_all(engine, when(5))[0]
    assert engine.db.execute("SELECT COUNT(*) FROM app_reminders").fetchone() == (0,)
    engine.snapshot(courses(when(10)), when(6))
    assert "Deadline changed" in accept_all(engine, when(6))[0]


def test_stale_summary_label_and_no_old_day_replay(engine):
    engine.snapshot(courses(when(10, 12)), when(5))
    accept_all(engine, when(5))
    engine.store.put("refresh_failed", True)
    engine.morning(when(10, 10))
    messages = accept_all(engine, when(10, 10))
    assert len(messages) == 1 and "last successful update" in messages[0]
    assert engine.db.execute("SELECT state FROM app_reminders WHERE days=3").fetchone() == ("skipped",)


def test_failed_send_stays_pending_and_retry_key_stable(engine):
    engine.snapshot(courses(when(10)), when(5))
    first = engine.prepare(engine.pending(when(5))[0], when(5))
    engine.failed(first[0], when(5))
    again = engine.prepare(engine.pending(when(5)+1000)[0], when(5)+1000)
    assert again == first
    assert engine.db.execute("SELECT state FROM app_outbox").fetchone() == ("pending",)


def test_partial_response_rolls_back_all_changes(engine):
    engine.snapshot(courses(when(10)), when(5))
    before = engine.db.execute("SELECT data FROM app_items").fetchone()
    bad = courses(when(15))
    bad[0]["assignments"].append({"id": "oops"})
    with pytest.raises(KeyError):
        engine.snapshot(bad, when(6))
    assert engine.db.execute("SELECT data FROM app_items").fetchone() == before


def test_line_accepted_retry_is_success():
    class Response:
        status_code = 409
        headers = {"x-line-accepted-request-id": "accepted"}
    class Session:
        def post(self, *args, **kwargs):
            return Response()
    Line("token", "recipient", Session()).send("hello", "00000000-0000-4000-8000-000000000001")


def test_line_bad_credentials_are_permanent_failure():
    class Response:
        status_code = 401
        headers = {}
    class Session:
        def post(self, *args, **kwargs):
            return Response()
    with pytest.raises(DeliveryError) as result:
        Line("token", "recipient", Session()).send("hello", "00000000-0000-4000-8000-000000000001")
    assert result.value.permanent
