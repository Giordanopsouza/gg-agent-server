"""SQLAlchemy metadata for the private application schemas.

The runtime ledger intentionally stores ISO-8601 timestamps and boolean flags
as text/integers because those representations are part of the existing data
contract.  Adopting SQLAlchemy must not silently rewrite persisted data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import conv


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Supabase Auth owns this table.  It is present only so SQLAlchemy can resolve
# application foreign keys; Alembic excludes objects carrying ``external``.
auth_users = Table(
    "users",
    Base.metadata,
    Column("id", PostgresUUID(as_uuid=True), primary_key=True),
    schema="auth",
    info={"external": True},
)


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = {"schema": "app_private"}

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class SchemaMeta(Base):
    __tablename__ = "schema_meta"
    __table_args__ = {"schema": "runtime_private"}

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("seq", name="tasks_seq_key"),
        Index("idx_tasks_seq", "seq"),
        Index(
            "tasks_operator_idempotency",
            "idempotency_key",
            unique=True,
            postgresql_where=text("owner_id IS NULL"),
        ),
        Index(
            "tasks_owner_idempotency",
            "owner_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("owner_id IS NOT NULL"),
        ),
        Index(
            "tasks_owner_seq",
            "owner_id",
            "seq",
            postgresql_where=text("owner_id IS NOT NULL"),
        ),
        {"schema": "runtime_private"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    repository: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    base_ref: Mapped[str | None] = mapped_column(Text)
    base_sha: Mapped[str | None] = mapped_column(Text)
    retry_of: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'z-ai/glm-5.3-flashx'")
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_detail: Mapped[str | None] = mapped_column(Text)
    check_status: Mapped[str | None] = mapped_column(Text)
    sandbox_cleanup_status: Mapped[str | None] = mapped_column(Text)
    payload_expired: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    owner_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))


class SandboxCreation(Base):
    __tablename__ = "sandbox_creations"
    __table_args__ = (
        UniqueConstraint(
            "deployment",
            "sandbox_name",
            name="sandbox_creations_deployment_sandbox_name_key",
        ),
        {"schema": "runtime_private"},
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_private.tasks.id"), primary_key=True
    )
    deployment: Mapped[str] = mapped_column(Text, nullable=False)
    sandbox_name: Mapped[str] = mapped_column(Text, nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False)
    session_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    credential_version: Mapped[int | None] = mapped_column(BigInteger)
    provider_id: Mapped[str | None] = mapped_column(Text)
    provider_state: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class TaskReservation(Base):
    __tablename__ = "task_reservations"
    __table_args__ = (
        Index("idx_reservations_reserved_at", "reserved_at"),
        {"schema": "runtime_private"},
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_private.tasks.id"), primary_key=True
    )
    phase: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[str | None] = mapped_column(Text)
    reserved_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class PublicationIntent(Base):
    __tablename__ = "publication_intents"
    __table_args__ = {"schema": "runtime_private"}

    task_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_private.tasks.id"), primary_key=True
    )
    repository: Mapped[str] = mapped_column(Text, nullable=False)
    task_branch: Mapped[str] = mapped_column(Text, nullable=False)
    base_ref: Mapped[str] = mapped_column(Text, nullable=False)
    task_marker: Mapped[str] = mapped_column(Text, nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    check_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    agent_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    pr_number: Mapped[int | None] = mapped_column(BigInteger)
    pr_url: Mapped[str | None] = mapped_column(Text)
    pr_draft: Mapped[int | None] = mapped_column(Integer)
    pr_author: Mapped[str | None] = mapped_column(Text)
    pr_state: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class TaskSupervision(Base):
    __tablename__ = "task_supervisions"
    __table_args__ = (
        UniqueConstraint("start_key", name="task_supervisions_start_key_key"),
        {"schema": "runtime_private"},
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_private.tasks.id"), primary_key=True
    )
    execution_id: Mapped[str] = mapped_column(Text, nullable=False)
    task_branch: Mapped[str] = mapped_column(Text, nullable=False)
    start_key: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    tail_gap_possible: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class TaskEventCopy(Base):
    __tablename__ = "task_event_copies"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "source_id",
            "source_seq",
            name="task_event_copies_task_id_source_id_source_seq_key",
        ),
        {"schema": "runtime_private"},
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_private.tasks.id"), primary_key=True
    )
    cursor_seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class TaskMessageReceipt(Base):
    __tablename__ = "task_message_receipts"
    __table_args__ = {"schema": "runtime_private"}

    task_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_private.tasks.id"), primary_key=True
    )
    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class TaskResult(Base):
    __tablename__ = "task_results"
    __table_args__ = {"schema": "runtime_private"}

    task_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_private.tasks.id"), primary_key=True
    )
    execution_id: Mapped[str | None] = mapped_column(Text)
    manifest_json: Mapped[str | None] = mapped_column(Text)
    evidence_complete: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    evidence_detail: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[str | None] = mapped_column(Text)


class RetentionTombstone(Base):
    __tablename__ = "retention_tombstones"
    __table_args__ = (
        UniqueConstraint("task_id", name="retention_tombstones_task_id_key"),
        Index(
            "tombstones_operator_idempotency",
            "idempotency_key",
            unique=True,
            postgresql_where=text("owner_id IS NULL"),
        ),
        Index(
            "tombstones_owner_idempotency",
            "owner_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("owner_id IS NOT NULL"),
        ),
        {"schema": "runtime_private"},
    )

    idempotency_key: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, nullable=False)
    repository: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    base_ref: Mapped[str | None] = mapped_column(Text)
    retry_of: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'z-ai/glm-5.3-flashx'")
    )
    terminal_state: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    remote_effect_json: Mapped[str | None] = mapped_column(Text)
    payload_expired_at: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))


class OpenRouterCredential(Base):
    __tablename__ = "openrouter_credentials"
    __table_args__ = (
        CheckConstraint("key_version > 0", name="key_version_check"),
        CheckConstraint("credential_version > 0", name="credential_version_check"),
        CheckConstraint("length(mask) <= 32", name="mask_check"),
        CheckConstraint(
            "(ciphertext IS NULL) = (mask IS NULL)",
            name=conv("credential_and_mask_together"),
        ),
        {"schema": "vault_private"},
    )

    owner_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_private.profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), nullable=False
    )
    credential_version: Mapped[int] = mapped_column(
        BigInteger, server_default=text("1"), nullable=False
    )
    mask: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class GitHubConnection(Base):
    __tablename__ = "github_connections"
    __table_args__ = (
        UniqueConstraint("github_user_id"),
        CheckConstraint("github_user_id > 0", name="github_user_id_positive"),
        CheckConstraint("key_version > 0", name="github_key_version_positive"),
        CheckConstraint(
            "status in ('connected','pending','revoked')", name="github_status_valid"
        ),
        {"schema": "vault_private"},
    )

    owner_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_private.profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    github_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    login: Mapped[str] = mapped_column(Text, nullable=False)
    token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class GitHubInstallation(Base):
    __tablename__ = "github_installations"
    __table_args__ = (
        CheckConstraint("installation_id > 0", name="installation_id_positive"),
        CheckConstraint(
            "status in ('active','removed')", name="installation_status_valid"
        ),
        Index("github_installations_id_idx", "installation_id"),
        {"schema": "app_private"},
    )

    owner_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_private.profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    installation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_login: Mapped[str] = mapped_column(Text, nullable=False)
    account_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class GitHubOAuthFlow(Base):
    __tablename__ = "github_oauth_flows"
    __table_args__ = (
        Index("github_oauth_flows_expiry_idx", "expires_at"),
        {"schema": "app_private"},
    )

    state_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_private.profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class GitHubWebhookDelivery(Base):
    __tablename__ = "github_webhook_deliveries"
    __table_args__ = (
        Index("github_webhook_deliveries_time_idx", "received_at"),
        {"schema": "app_private"},
    )

    delivery_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


APPLICATION_SCHEMAS = frozenset({"app_private", "runtime_private", "vault_private"})


def include_in_migrations(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """Keep Alembic autogeneration inside application-owned schemas."""
    del name, type_, reflected, compare_to
    table = obj if isinstance(obj, Table) else getattr(obj, "table", None)
    if table is not None and table.info.get("external"):
        return False
    schema = getattr(obj, "schema", None) or getattr(table, "schema", None)
    return schema is None or schema in APPLICATION_SCHEMAS
