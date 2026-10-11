"""Ledger behavior across independent SQLite connections and a restart."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from gg.runtime.ledger import TaskLedger
from gg.sdk.domain import Event, EventKind, MessageDeliveryStatus, MessageReceipt
from gg.sdk.task_execution import AgentOutcome, CheckOutcome
from test_support.sqlite_ledger import new_ledger


def _submit(ledger: TaskLedger, key: str):
    return ledger.submit(
        idempotency_key=key,
        repository="owner/repo",
        prompt="test task",
        base_ref="main",
        retry_of=None,
    )


def test_cross_connection_admission_claim_and_restart():
    def submit(index: int):
        with new_ledger() as ledger:
            return _submit(ledger, f"key-{index % 3}")

    with ThreadPoolExecutor(max_workers=6) as workers:
        submissions = list(workers.map(submit, range(12)))
    assert sum(created for _, created in submissions) == 3
    ids = {record.id for record, _ in submissions}
    assert len(ids) == 3
    assert len({record.seq for record, _ in submissions}) == 3

    def claim(_: int):
        with new_ledger() as ledger:
            return ledger.reserve_next(capacity=2)

    with ThreadPoolExecutor(max_workers=4) as workers:
        claims = list(workers.map(claim, range(4)))
    claimed_ids = [record.id for record in claims if record is not None]
    assert len(claimed_ids) == len(set(claimed_ids)) == 2
    with new_ledger() as restarted:
        assert ids == {record.id for record in restarted.list()}
        assert {record.task_id for record in restarted.list_reservations()} == set(
            claimed_ids
        )


def test_failed_write_rolls_back_and_evidence_survives_restart():
    with new_ledger() as ledger:
        task, _ = _submit(ledger, "rollback")
        with pytest.raises(RuntimeError, match="crash"):
            with ledger.db.write() as tx:
                tx.connection.execute(
                    "UPDATE tasks SET prompt = ? WHERE id = ?", ("uncommitted", task.id)
                )
                raise RuntimeError("crash")

    with new_ledger() as recovered:
        assert recovered.get(task.id).prompt == "test task"
        assert recovered.reserve_next(capacity=1).id == task.id
        assert (
            recovered.copy_task_event(
                task_id=task.id,
                source_id="execution",
                source_seq=1,
                event=Event(seq=1, kind=EventKind.STATUS, payload={"detail": "done"}),
            )
            == 1
        )
        recovered.archive_task_result(
            task_id=task.id,
            execution_id="execution",
            manifest=None,
            evidence_complete=True,
            evidence_detail=None,
        )
        receipt = MessageReceipt(
            id="message-1", content="continue", status=MessageDeliveryStatus.ACCEPTED
        )
        recovered.save_task_message_receipt(task.id, receipt)
        recovered.save_task_message_receipt(task.id, receipt)
        _, created = recovered.begin_publication(
            task_id=task.id,
            repository="owner/repo",
            task_branch="gg/task",
            base_ref="main",
            task_marker="task-marker",
            commit_sha=None,
            check_outcome=CheckOutcome.NOT_RUN,
            agent_outcome=AgentOutcome.SUCCEEDED,
        )
        assert created

    with new_ledger() as restarted:
        assert len(restarted.list_task_events(task.id)) == 1
        assert restarted.get_task_result(task.id).evidence_complete
        assert len(restarted.list_accepted_task_messages(task.id)) == 1
        assert restarted.get_publication(task.id) is not None
        _, created = restarted.begin_publication(
            task_id=task.id,
            repository="owner/repo",
            task_branch="gg/task",
            base_ref="main",
            task_marker="task-marker",
            commit_sha=None,
            check_outcome=CheckOutcome.NOT_RUN,
            agent_outcome=AgentOutcome.SUCCEEDED,
        )
        assert not created
