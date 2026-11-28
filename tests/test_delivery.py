import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path

from receiver.store import Store
from mcv_service.engine import Engine
from mcv_service.delivery import delivery_worker
from mcv_service.flex import assignment_messages


class DeliveryTests(unittest.TestCase):
    def test_command_wakes_idle_sender_during_refresh(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as folder:
                store = Store(Path(folder) / 'test.db')
                engine = Engine(store)
                stop = asyncio.Event()
                sent = threading.Event()
                refresh_started = asyncio.Event()
                finish_refresh = asyncio.Event()
                calls = []

                class Sender:
                    def send(self, messages, retry_key):
                        calls.append((messages, retry_key))
                        sent.set()

                async def refresh():
                    refresh_started.set()
                    await finish_refresh.wait()

                worker = asyncio.create_task(delivery_worker(engine, Sender(), stop))
                refresh_task = asyncio.create_task(refresh())
                try:
                    await refresh_started.wait()
                    # Let the sender become idle before the webhook-style queue write.
                    await asyncio.sleep(0.02)
                    with engine.db:
                        engine.queue_homework('webhook-1', time.time())
                    assert await asyncio.to_thread(sent.wait, 1)
                    assert not refresh_task.done()
                    await asyncio.sleep(0.02)
                    assert store.db.execute("SELECT state FROM app_outbox").fetchone() == ('sent',)
                    with engine.db:
                        engine.queue_homework('webhook-1', time.time())
                    await asyncio.sleep(0.02)
                    assert len(calls) == 1
                finally:
                    stop.set()
                    finish_refresh.set()
                    await asyncio.wait_for(worker, 1)
                    await refresh_task
                    store.close()
        asyncio.run(scenario())

    def test_failure_retains_backoff_and_retry_key(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as folder:
                store = Store(Path(folder) / 'test.db')
                engine = Engine(store)
                stop = asyncio.Event()
                calls = []

                class Sender:
                    def send(self, messages, retry_key):
                        calls.append((messages, retry_key))
                        if len(calls) == 1:
                            raise OSError('offline')

                with engine.db:
                    engine.queue_homework('retry', time.time())
                worker = asyncio.create_task(delivery_worker(engine, Sender(), stop))
                try:
                    for _ in range(100):
                        state, attempts, next_try = store.db.execute(
                            'SELECT state,attempts,next_try FROM app_outbox').fetchone()
                        if attempts:
                            break
                        await asyncio.sleep(0.01)
                    assert state == 'pending' and attempts == 1 and next_try > time.time()
                    engine.delivery_ready.set()
                    await asyncio.sleep(0.02)
                    assert len(calls) == 1
                    with engine.db:
                        engine.db.execute('UPDATE app_outbox SET next_try=0')
                    engine.delivery_ready.set()
                    for _ in range(100):
                        if store.db.execute('SELECT state FROM app_outbox').fetchone() == ('sent',):
                            break
                        await asyncio.sleep(0.01)
                    assert calls[0] == calls[1]
                    assert store.db.execute('SELECT state FROM app_outbox').fetchone() == ('sent',)
                finally:
                    stop.set()
                    await asyncio.wait_for(worker, 1)
                    store.close()
        asyncio.run(scenario())

    def test_assignment_layout_and_type_headers(self):
        item = dict(id='1:2', course='Control', title='HW 7', due=time.time()+86400, status='ASSIGNED')
        for kind, heading in [('new_assignment', 'NEW ASSIGNMENT'),
                              ('deadline_changed', 'DEADLINE UPDATED'),
                              ('deadline_summary', 'HOMEWORK DUE'),
                              ('initial_summary', 'HOMEWORK'),
                              ('homework', 'HOMEWORK')]:
            card = assignment_messages([item], 'Homework', time.time(), kind=kind, note='Last update: test')[0]['contents']['contents'][0]
            assert 'header' not in card and 'footer' not in card
            assert card['body']['contents'][0]['text'] == heading
            assert card['body']['contents'][0]['size'] == 'sm'
            assert card['body']['contents'][1]['text'] == 'Control'
            assert card['body']['contents'][1]['size'] == 'xl'
            assert card['body']['backgroundColor'].startswith('#')
            assert card['body']['contents'][2]['flex'] == 0
            content = card['body']['contents'][2]['contents']
            assert content[0]['text'] == 'HW 7' and content[0]['color'] == '#FFFFFF'
            assert content[0]['flex'] == 0 and content[0]['gravity'] == 'top'
            assert content[1]['contents'][0]['text'] == 'Due date:'
            assert content[2]['contents'][0]['text'] == 'Time left:'
            assert content[-1]['contents'][-1]['action']['label'] == 'Detail'
            assert '[NEW]' not in str(card) and '[Update]' not in str(card)
        card = assignment_messages([item], 'Homework', time.time())[0]['contents']['contents'][0]
        assert card['body']['contents'][1]['text'] == 'Control'
        assert card['body']['contents'][2]['contents'][-1]['contents'][-1]['action']['label'] == 'Detail'


if __name__ == '__main__':
    unittest.main()
