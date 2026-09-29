"""Track workspace retention independently from task history.

Revision ID: 0004_resumable_workspaces
Revises: 0003_github_connection
"""

from alembic import op


revision = "0004_resumable_workspaces"
down_revision = "0003_github_connection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "alter table runtime_private.tasks add column workspace_expired "
        "integer not null default 0"
    )
    op.execute(
        "alter table runtime_private.tasks add column workspace_last_activity_at text"
    )
    op.execute(
        "update runtime_private.schema_meta set value = '9' "
        "where key = 'schema_version' and value = '8'"
    )


def downgrade() -> None:
    op.execute(
        "alter table runtime_private.tasks drop column workspace_last_activity_at"
    )
    op.execute("alter table runtime_private.tasks drop column workspace_expired")
    op.execute(
        "update runtime_private.schema_meta set value = '8' "
        "where key = 'schema_version' and value = '9'"
    )
