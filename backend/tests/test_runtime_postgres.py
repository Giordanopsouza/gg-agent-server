"""Connection settings must select the intended role and pooler mode."""

import pytest

from gg.runtime.postgres import RuntimePostgres


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        (
            "postgresql://gg_runtime:secret@127.0.0.1:54322/postgres?sslmode=disable",
            True,
        ),
        (
            "postgresql://gg_runtime.xmqpgubedtjirohntdwg:secret@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=verify-full",
            True,
        ),
        (
            "postgresql://gg_runtime:secret@db.xmqpgubedtjirohntdwg.supabase.co:5432/postgres?sslmode=verify-full",
            False,
        ),
        (
            "postgresql://gg_runtime.xmqpgubedtjirohntdwg:secret@aws-0-us-west-2.pooler.supabase.com:6543/postgres?sslmode=verify-full",
            False,
        ),
        (
            "postgresql://postgres.xmqpgubedtjirohntdwg:secret@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=verify-full",
            False,
        ),
        (
            "postgresql://gg_runtime.xmqpgubedtjirohntdwg:secret@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=disable",
            False,
        ),
        (
            "postgresql://gg_runtime.xmqpgubedtjirohntdwg:secret@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=verify-full",
            False,
        ),
        (
            "postgresql://gg_runtime.xmqpgubedtjirohntdwg:secret@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=verify-full&sslmode=disable",
            False,
        ),
        (
            "postgresql://gg_runtime.xmqpgubedtjirohntdwg:secret@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=verify-full&host=example.com",
            False,
        ),
    ],
)
def test_runtime_connection_mode(
    monkeypatch: pytest.MonkeyPatch, url: str, allowed: bool
) -> None:
    monkeypatch.setenv("GG_RUNTIME_DATABASE_URL", url)
    if allowed:
        assert RuntimePostgres.from_env().url == url
    else:
        with pytest.raises(ValueError):
            RuntimePostgres.from_env()


@pytest.mark.parametrize("size", ["0", "9", "garbage"])
def test_runtime_pool_size_is_bounded(
    monkeypatch: pytest.MonkeyPatch, size: str
) -> None:
    monkeypatch.setenv(
        "GG_RUNTIME_DATABASE_URL",
        "postgresql://gg_runtime:secret@127.0.0.1:54322/postgres?sslmode=disable",
    )
    monkeypatch.setenv("GG_DB_POOL_MAX", size)
    with pytest.raises(ValueError):
        RuntimePostgres.from_env()


def test_hosted_pool_uses_bundled_ca() -> None:
    config = RuntimePostgres(
        "postgresql://gg_runtime.xmqpgubedtjirohntdwg:secret@"
        "aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=verify-full"
    )
    with config.pool() as pool:
        assert pool.kwargs["sslrootcert"].endswith("supabase-prod-ca-2021.crt")
        assert pool.kwargs["prepare_threshold"] is None
