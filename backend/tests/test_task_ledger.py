"""Durable ledger behavior against isolated SQLite."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from gg.runtime.ledger import TaskLedger
from test_support.sqlite_ledger import new_ledger


def _submit(ledger: TaskLedger, key: str):
    return ledger.submit(
        idempotency_key=key,
        repository="owner/name",
        prompt="work",
        base_ref=None,
        retry_of=None,
    )


def test_sequence_idempotency_and_restart() -> None:
    with new_ledger() as ledger:
        first, created = _submit(ledger, "k1")
        replay, replay_created = _submit(ledger, "k1")
        second, second_created = _submit(ledger, "k2")

    with new_ledger() as restarted:
        records = restarted.list()
        missing = restarted.get("missing")

    assert created and second_created and not replay_created
    assert replay.id == first.id
    assert second.seq == first.seq + 1
    assert [record.id for record in records] == [first.id, second.id]
    assert missing is None


def test_concurrent_duplicate_submissions_insert_once() -> None:
    with new_ledger() as ledger:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: _submit(ledger, "race"), range(16)))
        assert len(ledger.list()) == 1

    assert sum(created for _, created in results) == 1
    assert len({record.id for record, _ in results}) == 1


def test_provider_observations_only_write_effective_changes():
    from gg.runtime.ledger import SandboxProviderState

    with new_ledger() as ledger:
        task, _ = _submit(ledger, "provider-noop")
        ledger.begin_sandbox_creation(
            task_id=task.id,
            deployment="test",
            sandbox_name="test",
            tags_json="{}",
            session_api_key="private",
        )
        first = ledger.update_sandbox_creation(
            task.id,
            provider_id="sb-first",
            provider_state=SandboxProviderState.RUNNING,
        )
        revision = ledger.db.revision
        with ThreadPoolExecutor(max_workers=4) as pool:
            copies = list(
                pool.map(
                    lambda _: ledger.update_sandbox_creation(
                        task.id,
                        provider_state=SandboxProviderState.RUNNING,
                    ),
                    range(4),
                )
            )
        assert ledger.db.revision == revision
        assert all(
            copy.updated_at == first.updated_at and copy.provider_id == "sb-first"
            for copy in copies
        )
        error = ledger.update_sandbox_creation(
            task.id,
            provider_state=SandboxProviderState.UNKNOWN,
            detail="lookup failed",
        )
        assert ledger.db.revision == revision + 1 and error.detail == "lookup failed"
        recovered = ledger.update_sandbox_creation(
            task.id,
            provider_id="sb-new",
            provider_state=SandboxProviderState.RUNNING,
        )
        assert ledger.db.revision == revision + 2
        assert recovered.provider_id == "sb-new" and recovered.detail is None
