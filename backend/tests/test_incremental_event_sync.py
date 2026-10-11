"""Real HTTP event pagination and atomic SQLite page recovery."""

import sqlite3
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from gg.runtime.ledger import TaskLedger
from gg.runtime.sqlite_db import SQLiteDB, initialize
from gg.runtime.task_supervision.manager import (
    SupervisionCallbacks,
    TaskSupervisionManager,
)
from gg.sdk.domain import Event, EventKind


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / "runtime.db"
    initialize(path)
    with SQLiteDB(path) as db:
        yield TaskLedger(db)


def task(ledger):
    return ledger.submit(
        idempotency_key="page",
        repository=None,
        prompt="work",
        base_ref=None,
        retry_of=None,
    )[0]


def events(count, start=1):
    return [
        Event(seq=seq, kind=EventKind.MESSAGE, payload={"text": "á" * 2000})
        for seq in range(start, start + count)
    ]


def test_page_rollback_dedup_and_independent_conversation(ledger):
    record = task(ledger)
    page = events(3)
    with ledger.db.write() as tx:
        tx.connection.execute("""CREATE TRIGGER fail_page
        BEFORE INSERT ON task_event_copies
        WHEN NEW.source_seq = 2 BEGIN SELECT RAISE(ABORT, 'injected'); END""")
    revision = ledger.db.revision
    with pytest.raises(sqlite3.IntegrityError):
        ledger.copy_task_event_page(task_id=record.id, source_id="first", events=page)
    assert ledger.db.revision == revision
    assert ledger.event_source_cursor(record.id, "first") == 0
    assert ledger.list_task_events(record.id) == []
    with ledger.db.write() as tx:
        tx.connection.execute("DROP TRIGGER fail_page")
    # Existing evidence from an older writer is deduplicated on first paged sync.
    ledger.copy_task_event(
        task_id=record.id, source_id="first", source_seq=1, event=page[0]
    )
    assert [
        cursor
        for cursor, _ in ledger.copy_task_event_page(
            task_id=record.id, source_id="first", events=page
        )
    ] == [2, 3]
    assert (
        ledger.copy_task_event_page(task_id=record.id, source_id="first", events=page)
        == []
    )
    assert ledger.event_source_cursor(record.id, "first") == 3
    assert ledger.event_source_cursor(record.id, "second") == 0
    assert (
        ledger.copy_task_event_page(
            task_id=record.id, source_id="second", events=page[:1]
        )[0][0]
        == 4
    )


class Connection:
    def __init__(self, history):
        self.history = history
        self.requests = []
        self.fail_after = None

    @asynccontextmanager
    async def http_client(self, **kwargs):
        def respond(request):
            after = int(request.url.params["after"])
            limit = int(request.url.params["limit"])
            self.requests.append((after, limit))
            if after == self.fail_after:
                raise httpx.ReadError("restart between pages")
            page = [e for e in self.history if e.seq > after][:limit]
            return httpx.Response(200, json=[e.model_dump(mode="json") for e in page])

        async with httpx.AsyncClient(
            base_url="http://sandbox", transport=httpx.MockTransport(respond), **kwargs
        ) as client:
            yield client


@pytest.mark.anyio
async def test_450_events_resume_after_restart_and_notify_only_inserts(ledger):
    record = task(ledger)
    history = events(450)
    connection = Connection(history)
    callbacks = []

    def manager(store):
        return TaskSupervisionManager(
            ledger=store,
            lifecycle=None,
            settings=SimpleNamespace(),
            callbacks=SupervisionCallbacks(
                on_event_copied=lambda tid, cursor, event: callbacks.append(cursor)
            ),
        )

    first = manager(ledger)
    live = first.subscribe_events(record.id)
    connection.fail_after = 200
    with pytest.raises(httpx.ReadError):
        await first._sync_events(record.id, connection, "conversation")
    assert ledger.event_source_cursor(record.id, "conversation") == 200
    assert live.qsize() == 200
    path = ledger.db.path
    ledger.db.close()
    with SQLiteDB(path) as reopened:
        fresh_ledger = TaskLedger(reopened)
        fresh = manager(fresh_ledger)
        queue = fresh.subscribe_events(record.id)
        connection.fail_after = None
        await fresh._sync_events(record.id, connection, "conversation")
        assert connection.requests == [(0, 200), (200, 200), (200, 200), (400, 200)]
        assert [
            event for _, _, _, event in fresh_ledger.list_task_events(record.id)
        ] == history
        assert callbacks == list(range(1, 451))
        assert queue.qsize() == 250
        await fresh._sync_events(record.id, connection, "conversation")
        assert connection.requests[-1] == (450, 200)
        assert queue.qsize() == 250


@pytest.mark.anyio
async def test_truncation_advances_cursor_and_live_matches_persisted(ledger):
    record = task(ledger)
    manager = TaskSupervisionManager(
        ledger=ledger, lifecycle=None, settings=SimpleNamespace()
    )
    manager._storage_limits = SimpleNamespace(max_log_evidence_bytes=1024)
    queue = manager.subscribe_events(record.id)
    connection = Connection(events(201))
    await manager._sync_events(record.id, connection, "conversation")
    assert ledger.event_source_cursor(record.id, "conversation") == 201
    stored = ledger.list_task_events(record.id)
    assert len(stored) == 201
    assert all(len(event.model_dump_json().encode()) < 1024 for *_, event in stored)
    assert [queue.get_nowait().event for _ in stored] == [event for *_, event in stored]
    assert connection.requests == [(0, 200), (200, 200)]
