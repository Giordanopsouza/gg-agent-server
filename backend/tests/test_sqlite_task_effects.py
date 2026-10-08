"""Intent/confirmation restart demos and atomic rollback."""

import sqlite3

import pytest

from gg.runtime.ledger import (
    PublicationIdentityError,
    SandboxProviderState,
    SupervisionIdentityError,
    TaskLedger,
)
from gg.runtime.sqlite_db import SQLiteDB, initialize
from gg.sdk.domain import MessageDeliveryStatus, MessageReceipt
from gg.sdk.publication import PublicationState
from gg.sdk.task_execution import AgentOutcome, CheckOutcome
from gg.sdk.tasks import TaskState


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "runtime.db"
    initialize(path)
    with SQLiteDB(path) as database:
        yield database


def submit(ledger, key="key", owner=None):
    return ledger.submit(
        idempotency_key=key,
        owner_id=owner,
        repository=None,
        prompt="work ' ; --",
        base_ref=None,
        retry_of=None,
    )


def creation(ledger, task_id, **changes):
    fields = dict(
        task_id=task_id,
        deployment="test",
        sandbox_name=task_id,
        tags_json='{"task": "test"}',
        session_api_key="private-test-key",
        credential_version=2,
    )
    return ledger.begin_sandbox_creation(**(fields | changes))


def supervision(ledger, task_id, **changes):
    return ledger.begin_supervision(
        **(
            dict(
                task_id=task_id,
                execution_id="execution",
                task_branch="gg/task",
                start_key=task_id,
                conversation_id="conversation",
            )
            | changes
        )
    )


def publication(ledger, task_id, **changes):
    return ledger.begin_publication(
        **(
            dict(
                task_id=task_id,
                repository="owner/repo",
                task_branch="gg/task",
                base_ref="main",
                task_marker="marker",
                commit_sha="sha",
                check_outcome=CheckOutcome.PASSED,
                agent_outcome=AgentOutcome.SUCCEEDED,
            )
            | changes
        )
    )


def test_restart_between_intentions_and_confirmation(db):
    ledger = TaskLedger(db)
    task, _ = submit(ledger)
    original = [
        creation(ledger, task.id)[0],
        supervision(ledger, task.id)[0],
        publication(ledger, task.id)[0],
    ]
    ledger.record_base_sha(task.id, "base-sha")
    db.close()
    with SQLiteDB(db.path) as reopened:
        ledger = TaskLedger(reopened)
        replay = [
            creation(ledger, task.id),
            supervision(ledger, task.id),
            publication(ledger, task.id),
        ]
        assert [r for r, _ in replay] == original
        assert not any(created for _, created in replay)
        assert ledger.get(task.id).base_sha == "base-sha"
        ledger.set_sandbox_credential_version(task.id, 3)
        ledger.update_sandbox_creation(
            task.id, provider_id="provider", provider_state=SandboxProviderState.RUNNING
        )
        ledger.update_publication(
            task.id,
            state=PublicationState.PUBLISHED,
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_draft=False,
            pr_state="open",
            outcome_detail="published",
            check_status="passed",
        )
        assert ledger.request_task_cancel(task.id).cancel_requested
    with SQLiteDB(db.path) as reopened:
        ledger = TaskLedger(reopened)
        assert ledger.get_sandbox_creation(task.id).provider_id == "provider"
        assert ledger.get_sandbox_creation(task.id).credential_version == 3
        assert ledger.get_supervision(task.id).cancel_requested
        assert ledger.get_publication(task.id).pr_number == 42
        assert ledger.get_publication(task.id).pr_draft is False
        assert ledger.get(task.id).outcome_detail == "published"


@pytest.mark.parametrize(
    "kind,change,error",
    [
        ("creation", {"sandbox_name": "wrong"}, RuntimeError),
        ("creation", {"tags_json": "{}"}, RuntimeError),
        ("supervision", {"execution_id": "wrong"}, SupervisionIdentityError),
        ("supervision", {"task_branch": "wrong"}, SupervisionIdentityError),
        ("publication", {"task_marker": "wrong"}, PublicationIdentityError),
        ("publication", {"commit_sha": "wrong"}, PublicationIdentityError),
    ],
)
def test_identity_conflicts_do_not_commit(db, kind, change, error):
    ledger = TaskLedger(db)
    task, _ = submit(ledger)
    operation = {
        "creation": creation,
        "supervision": supervision,
        "publication": publication,
    }[kind]
    original, _ = operation(ledger, task.id)
    revision = db.revision
    with pytest.raises(error):
        operation(ledger, task.id, **change)
    assert db.revision == revision
    assert operation(ledger, task.id)[0] == original


def test_start_key_cannot_belong_to_two_tasks(db):
    ledger = TaskLedger(db)
    first, _ = submit(ledger)
    second, _ = submit(ledger, "second")
    supervision(ledger, first.id)
    with pytest.raises(SupervisionIdentityError):
        supervision(ledger, second.id, start_key=first.id)
    assert ledger.get_supervision(second.id) is None


def test_receipts_are_idempotent_and_conflicts_rollback(db):
    ledger = TaskLedger(db)
    task, _ = submit(ledger)
    receipt = MessageReceipt(
        id="message", content="hello", status=MessageDeliveryStatus.ACCEPTED
    )
    ledger.save_task_message_receipt(task.id, receipt)
    ledger.save_task_message_receipt(task.id, receipt)
    assert ledger.list_accepted_task_messages(task.id) == [receipt]
    revision = db.revision
    with pytest.raises(RuntimeError, match="another message"):
        ledger.save_task_message_receipt(
            task.id, receipt.model_copy(update={"content": "different"})
        )
    assert db.revision == revision
    delivered = receipt.model_copy(update={"status": MessageDeliveryStatus.DELIVERED})
    ledger.save_task_message_receipt(task.id, delivered)
    with SQLiteDB(db.path) as reopened:
        assert (
            TaskLedger(reopened).get_task_message_receipt(task.id, "message")
            == delivered
        )


def test_publication_partial_update_rolls_back(db):
    ledger = TaskLedger(db)
    task, _ = submit(ledger)
    original, _ = publication(ledger, task.id)
    with db.write() as tx:
        tx.connection.execute(
            """
            CREATE TRIGGER reject_outcome BEFORE UPDATE ON tasks BEGIN SELECT
            RAISE(ABORT, 'injected failure'); END
            """
        )
    revision = db.revision
    with pytest.raises(sqlite3.IntegrityError):
        ledger.update_publication(
            task.id,
            state=PublicationState.PUBLISHED,
            pr_number=42,
            outcome_detail="published",
        )
    assert ledger.get_publication(task.id) == original
    assert db.revision == revision


def test_workspace_cancel_and_success_settlement(db):
    ledger = TaskLedger(db)
    task, _ = submit(ledger)
    assert ledger.cancel_queued_task(task.id).state is TaskState.CANCELLED
    task, _ = submit(ledger, "workspace")
    ledger.reserve_next(capacity=10)
    ledger.finish_task(task.id, state=TaskState.IDLE)
    assert ledger.try_mark_sleeping(task.id)
    ledger.expire_workspace(task.id)
    assert ledger.get(task.id).workspace_expired
    ledger.queue_workspace_message(task.id)
    ledger.touch_workspace(task.id)
    assert ledger.get(task.id).state is TaskState.QUEUED
    assert ledger.get(task.id).workspace_last_activity_at is not None
    creation(ledger, task.id)
    ledger.update_sandbox_creation(
        task.id, provider_id="old", provider_state=SandboxProviderState.STOPPED
    )
    ledger.reset_sandbox_for_wake(task.id)
    assert ledger.get_sandbox_creation(task.id).provider_id is None
    ledger.finish_task(
        task.id, state=TaskState.FINALIZING, outcome_detail="checks_passed"
    )
    ledger.mark_sandbox_lost(task.id, detail="gone")
    ledger.settle_successful_tasks()
    with SQLiteDB(db.path) as reopened:
        assert TaskLedger(reopened).get(task.id).state is TaskState.COMPLETED
        assert TaskLedger(reopened).list_reservations() == []
