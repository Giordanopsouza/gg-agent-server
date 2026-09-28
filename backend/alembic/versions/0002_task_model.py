"""Persist the effective model on tasks and idempotency tombstones.

Revision ID: 0002_task_model
Revises: 0001_application_baseline
"""

from alembic import op


revision = "0002_task_model"
down_revision = "0001_application_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "alter table runtime_private.tasks add column model text "
        "not null default 'z-ai/glm-5.3-flashx'"
    )
    op.execute(
        "alter table runtime_private.retention_tombstones add column model text "
        "not null default 'z-ai/glm-5.3-flashx'"
    )
    op.execute(
        "alter table runtime_private.sandbox_creations "
        "add column credential_version bigint"
    )
    op.execute(
        "update runtime_private.schema_meta set value = '8' "
        "where key = 'schema_version' and value = '7'"
    )


def downgrade() -> None:
    op.execute(
        "alter table runtime_private.sandbox_creations drop column credential_version"
    )
    op.execute("alter table runtime_private.retention_tombstones drop column model")
    op.execute("alter table runtime_private.tasks drop column model")
    op.execute(
        "update runtime_private.schema_meta set value = '7' "
        "where key = 'schema_version' and value = '8'"
    )
