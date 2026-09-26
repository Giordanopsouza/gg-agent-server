"""Environment-backed configuration for the standalone runtime process."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001
DEFAULT_TASK_DB_PATH = "gg-tasks.sqlite"
DEFAULT_MAX_PROMPT_CHARS = 16_000
DEFAULT_MAX_BASE_REF_CHARS = 200
DEFAULT_MAX_IDEMPOTENCY_KEY_CHARS = 256
DEFAULT_MODAL_APP_NAME = "gg-agent-sandboxes"
DEFAULT_MODAL_DEPLOYMENT = "gg-production"
DEFAULT_MODAL_IMAGE_NAME = "gg-agent-server:2026-09-20-v1"
DEFAULT_MODAL_CPU_REQUEST = 2.0
DEFAULT_MODAL_CPU_LIMIT = 2.0
DEFAULT_MODAL_MEMORY_REQUEST_MIB = 4096
DEFAULT_MODAL_MEMORY_LIMIT_MIB = 4096
DEFAULT_MODAL_STARTUP_TIMEOUT_SECONDS = 5 * 60
DEFAULT_MODAL_PROVIDER_TIMEOUT_SECONDS = 70 * 60
DEFAULT_TASK_CAPACITY = 10
DEFAULT_DISPATCH_POLL_SECONDS = 1.0
DEFAULT_TERMINAL_RETENTION_DAYS = 7
DEFAULT_TOMBSTONE_RETENTION_DAYS = 90
DEFAULT_MAX_LOG_EVIDENCE_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_ARTIFACT_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_TOTAL_EVIDENCE_BYTES = 5 * 1024 * 1024 * 1024
DEFAULT_MIN_FREE_DISK_BYTES = 1024 * 1024 * 1024
SUPPORTED_TASK_SCHEMA_VERSION = 3


class RuntimeSettings(BaseModel):
    """Frozen settings for the control plane and its sandbox image."""

    model_config = ConfigDict(frozen=True)

    api_key: str
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    web_cookie_key: str | None = None
    web_origin: str | None = None
    web_cookie_secure: bool = True
    cors_origins: tuple[str, ...] = ()
    host: str = DEFAULT_HOST
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    task_db_path: str = DEFAULT_TASK_DB_PATH
    github_clone_token: str | None = None
    openrouter_api_key: str | None = None
    max_prompt_chars: int = Field(default=DEFAULT_MAX_PROMPT_CHARS, ge=1)
    max_base_ref_chars: int = Field(default=DEFAULT_MAX_BASE_REF_CHARS, ge=1)
    max_idempotency_key_chars: int = Field(
        default=DEFAULT_MAX_IDEMPOTENCY_KEY_CHARS, ge=1
    )
    modal_app_name: str = DEFAULT_MODAL_APP_NAME
    modal_deployment: str = DEFAULT_MODAL_DEPLOYMENT
    modal_image_name: str = DEFAULT_MODAL_IMAGE_NAME
    modal_cpu_request: float = Field(default=DEFAULT_MODAL_CPU_REQUEST, gt=0)
    modal_cpu_limit: float = Field(default=DEFAULT_MODAL_CPU_LIMIT, gt=0)
    modal_memory_request_mib: int = Field(
        default=DEFAULT_MODAL_MEMORY_REQUEST_MIB, ge=1
    )
    modal_memory_limit_mib: int = Field(default=DEFAULT_MODAL_MEMORY_LIMIT_MIB, ge=1)
    modal_startup_timeout_seconds: int = Field(
        default=DEFAULT_MODAL_STARTUP_TIMEOUT_SECONDS, ge=1
    )
    modal_provider_timeout_seconds: int = Field(
        default=DEFAULT_MODAL_PROVIDER_TIMEOUT_SECONDS, ge=1, le=24 * 60 * 60
    )
    task_capacity: int = Field(default=DEFAULT_TASK_CAPACITY, ge=1, le=10)
    dispatch_poll_seconds: float = Field(default=DEFAULT_DISPATCH_POLL_SECONDS, gt=0)
    task_dispatch_enabled: bool = False
    dispatch_lock_path: str | None = None
    task_evidence_dir: str | None = None
    terminal_retention_days: int = Field(default=DEFAULT_TERMINAL_RETENTION_DAYS, ge=1)
    tombstone_retention_days: int = Field(
        default=DEFAULT_TOMBSTONE_RETENTION_DAYS, ge=1
    )
    max_log_evidence_bytes: int = Field(default=DEFAULT_MAX_LOG_EVIDENCE_BYTES, ge=1024)
    max_artifact_bytes: int = Field(default=DEFAULT_MAX_ARTIFACT_BYTES, ge=1024)
    max_total_evidence_bytes: int = Field(
        default=DEFAULT_MAX_TOTAL_EVIDENCE_BYTES, ge=1024
    )
    min_free_disk_bytes: int = Field(default=DEFAULT_MIN_FREE_DISK_BYTES, ge=0)

    @field_validator("api_key")
    @classmethod
    # The control-plane key must be present and not have stray spaces.
    def validate_api_key(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError(
                "api_key must be non-empty and cannot contain surrounding whitespace"
            )
        return value

    @field_validator("supabase_url", "web_origin")
    @classmethod
    def validate_web_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if (
                not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.scheme not in ("https", "http")
                or (
                    parsed.scheme == "http"
                    and parsed.hostname not in ("localhost", "127.0.0.1")
                )
            ):
                raise ValueError(
                    "web URLs must be HTTPS origins or loopback HTTP origins"
                )
        return value

    @model_validator(mode="after")
    def validate_web_cookie_settings(self) -> RuntimeSettings:
        if self.web_cookie_key is not None:
            try:
                Fernet(self.web_cookie_key)
            except (ValueError, TypeError) as exc:
                raise ValueError("web_cookie_key must be a Fernet key") from exc
        if not self.web_cookie_secure and self.web_origin:
            if urlsplit(self.web_origin).hostname not in ("localhost", "127.0.0.1"):
                raise ValueError("insecure web cookies are allowed only on loopback")
        return self

    @field_validator("task_db_path")
    @classmethod
    # The SQLite path must be usable; ":memory:" is allowed for tests.
    def validate_task_db_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task_db_path must not be empty")
        return value

    @field_validator("modal_app_name", "modal_deployment", "modal_image_name")
    @classmethod
    def validate_modal_names(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("Modal names must be non-empty without surrounding spaces")
        return value

    @field_validator("modal_cpu_limit")
    @classmethod
    def validate_cpu_limit(cls, value: float, info: ValidationInfo) -> float:
        # Pydantic validates fields in declaration order, so the request is available.
        request = info.data.get("modal_cpu_request")
        if request is not None and value < request:
            raise ValueError("modal_cpu_limit must be at least modal_cpu_request")
        return value

    @field_validator("modal_memory_limit_mib")
    @classmethod
    def validate_memory_limit(cls, value: int, info: ValidationInfo) -> int:
        request = info.data.get("modal_memory_request_mib")
        if request is not None and value < request:
            raise ValueError(
                "modal_memory_limit_mib must be at least modal_memory_request_mib"
            )
        return value

    @field_validator("dispatch_lock_path")
    @classmethod
    def validate_dispatch_lock_path(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("dispatch_lock_path must be non-empty when provided")
        return value

    @field_validator("task_evidence_dir")
    @classmethod
    def validate_task_evidence_dir(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("task_evidence_dir must be non-empty when provided")
        return value

    @field_validator("tombstone_retention_days")
    @classmethod
    def validate_tombstone_retention(cls, value: int, info: ValidationInfo) -> int:
        terminal = info.data.get("terminal_retention_days")
        if terminal is not None and value < terminal:
            raise ValueError(
                "tombstone_retention_days must be at least terminal_retention_days"
            )
        return value


# Turn GG_RUNTIME_PORT into an int, or use 8001 if unset.
def _parse_port(raw: str | None) -> int:
    if raw is None or raw == "":
        return DEFAULT_PORT
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"GG_RUNTIME_PORT must be an integer, got {raw!r}") from exc
    if not (1 <= value <= 65535):
        raise ValueError(f"GG_RUNTIME_PORT must be between 1 and 65535, got {value}")
    return value


def _optional_secret(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def _parse_int(raw: str | None, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"expected an integer, got {raw!r}") from exc


def _parse_float(raw: str | None, default: float) -> float:
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"expected a number, got {raw!r}") from exc


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"expected a boolean, got {raw!r}")


# Read all runtime settings from environment variables at startup.
def load_settings() -> RuntimeSettings:
    """Read runtime configuration once at the process boundary."""
    api_key = os.getenv("GG_RUNTIME_API_KEY")
    if api_key is None or not api_key.strip():
        raise ValueError("GG_RUNTIME_API_KEY must be set to a non-empty value")
    if api_key != api_key.strip():
        raise ValueError("GG_RUNTIME_API_KEY cannot contain surrounding whitespace")

    return RuntimeSettings(
        api_key=api_key,
        supabase_url=_optional_secret(os.getenv("GG_SUPABASE_URL")),
        supabase_publishable_key=_optional_secret(
            os.getenv("GG_SUPABASE_PUBLISHABLE_KEY")
        ),
        web_cookie_key=_optional_secret(os.getenv("GG_WEB_COOKIE_KEY")),
        web_origin=_optional_secret(os.getenv("GG_WEB_ORIGIN")),
        web_cookie_secure=_parse_bool(os.getenv("GG_WEB_COOKIE_SECURE"), True),
        cors_origins=tuple(
            origin.strip()
            for origin in os.getenv("GG_RUNTIME_CORS_ORIGINS", "").split(",")
            if origin.strip()
        ),
        host=os.getenv("GG_RUNTIME_HOST", DEFAULT_HOST),
        port=_parse_port(os.getenv("GG_RUNTIME_PORT")),
        task_db_path=os.getenv("GG_TASK_DB_PATH", DEFAULT_TASK_DB_PATH),
        github_clone_token=_optional_secret(os.getenv("GG_GITHUB_CLONE_TOKEN")),
        openrouter_api_key=_optional_secret(os.getenv("OPENROUTER_API_KEY")),
        max_prompt_chars=_parse_int(
            os.getenv("GG_MAX_PROMPT_CHARS"), DEFAULT_MAX_PROMPT_CHARS
        ),
        max_base_ref_chars=_parse_int(
            os.getenv("GG_MAX_BASE_REF_CHARS"), DEFAULT_MAX_BASE_REF_CHARS
        ),
        max_idempotency_key_chars=_parse_int(
            os.getenv("GG_MAX_IDEMPOTENCY_KEY_CHARS"),
            DEFAULT_MAX_IDEMPOTENCY_KEY_CHARS,
        ),
        modal_app_name=os.getenv("GG_MODAL_APP_NAME", DEFAULT_MODAL_APP_NAME),
        modal_deployment=os.getenv("GG_MODAL_DEPLOYMENT", DEFAULT_MODAL_DEPLOYMENT),
        modal_image_name=os.getenv("GG_MODAL_IMAGE_NAME", DEFAULT_MODAL_IMAGE_NAME),
        modal_cpu_request=float(
            os.getenv("GG_MODAL_CPU_REQUEST", str(DEFAULT_MODAL_CPU_REQUEST))
        ),
        modal_cpu_limit=float(
            os.getenv("GG_MODAL_CPU_LIMIT", str(DEFAULT_MODAL_CPU_LIMIT))
        ),
        modal_memory_request_mib=_parse_int(
            os.getenv("GG_MODAL_MEMORY_REQUEST_MIB"),
            DEFAULT_MODAL_MEMORY_REQUEST_MIB,
        ),
        modal_memory_limit_mib=_parse_int(
            os.getenv("GG_MODAL_MEMORY_LIMIT_MIB"), DEFAULT_MODAL_MEMORY_LIMIT_MIB
        ),
        modal_startup_timeout_seconds=_parse_int(
            os.getenv("GG_MODAL_STARTUP_TIMEOUT_SECONDS"),
            DEFAULT_MODAL_STARTUP_TIMEOUT_SECONDS,
        ),
        modal_provider_timeout_seconds=_parse_int(
            os.getenv("GG_MODAL_PROVIDER_TIMEOUT_SECONDS"),
            DEFAULT_MODAL_PROVIDER_TIMEOUT_SECONDS,
        ),
        task_capacity=_parse_int(os.getenv("GG_TASK_CAPACITY"), DEFAULT_TASK_CAPACITY),
        dispatch_poll_seconds=_parse_float(
            os.getenv("GG_DISPATCH_POLL_SECONDS"), DEFAULT_DISPATCH_POLL_SECONDS
        ),
        task_dispatch_enabled=_parse_bool(os.getenv("GG_TASK_DISPATCH_ENABLED")),
        dispatch_lock_path=os.getenv("GG_DISPATCH_LOCK_PATH"),
        task_evidence_dir=os.getenv("GG_TASK_EVIDENCE_DIR"),
        terminal_retention_days=_parse_int(
            os.getenv("GG_TERMINAL_RETENTION_DAYS"), DEFAULT_TERMINAL_RETENTION_DAYS
        ),
        tombstone_retention_days=_parse_int(
            os.getenv("GG_TOMBSTONE_RETENTION_DAYS"), DEFAULT_TOMBSTONE_RETENTION_DAYS
        ),
        max_log_evidence_bytes=_parse_int(
            os.getenv("GG_MAX_LOG_EVIDENCE_BYTES"), DEFAULT_MAX_LOG_EVIDENCE_BYTES
        ),
        max_artifact_bytes=_parse_int(
            os.getenv("GG_MAX_ARTIFACT_BYTES"), DEFAULT_MAX_ARTIFACT_BYTES
        ),
        max_total_evidence_bytes=_parse_int(
            os.getenv("GG_MAX_TOTAL_EVIDENCE_BYTES"),
            DEFAULT_MAX_TOTAL_EVIDENCE_BYTES,
        ),
        min_free_disk_bytes=_parse_int(
            os.getenv("GG_MIN_FREE_DISK_BYTES"), DEFAULT_MIN_FREE_DISK_BYTES
        ),
    )
