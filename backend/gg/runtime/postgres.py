"""Bounded SQLAlchemy/Postgres engine configuration for the runtime."""

import os
from dataclasses import dataclass
from importlib.resources import files
from urllib.parse import parse_qs, unquote, urlsplit

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url


PRODUCTION_POOLER_HOST = "aws-0-us-west-2.pooler.supabase.com"


@dataclass(frozen=True)
class RuntimePostgres:
    url: str
    max_size: int = 4
    schema: str = "runtime_private"

    @classmethod
    def from_env(cls) -> "RuntimePostgres":
        url = os.environ["GG_RUNTIME_DATABASE_URL"]
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"postgresql", "postgres"}
            or not parsed.hostname
            or not parsed.password
            or parsed.path != "/postgres"
            or parsed.fragment
        ):
            raise ValueError("GG_RUNTIME_DATABASE_URL must be a Postgres URL")
        username = unquote(parsed.username or "")
        query = parse_qs(parsed.query, keep_blank_values=True)
        if set(query) != {"sslmode"} or len(query["sslmode"]) != 1:
            raise ValueError("Unsupported Postgres URL parameters")
        sslmode = query["sslmode"][0]
        local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if local:
            if username != "gg_runtime" or parsed.port != 54322:
                raise ValueError("Local runtime requires gg_runtime on port 54322")
            # The local CLI database does not terminate TLS.
            if sslmode != "disable":
                raise ValueError("Local Postgres requires sslmode=disable")
        else:
            if (
                username != "gg_runtime.xmqpgubedtjirohntdwg"
                or parsed.hostname != PRODUCTION_POOLER_HOST
                or parsed.port != 5432
            ):
                raise ValueError("Production requires the project session pooler")
            if sslmode != "verify-full":
                raise ValueError("Production Postgres requires sslmode=verify-full")
        max_size = int(os.environ.get("GG_DB_POOL_MAX", "4"))
        if not 1 <= max_size <= 8:
            raise ValueError("GG_DB_POOL_MAX must be between 1 and 8")
        return cls(url=url, max_size=max_size)

    def engine(self) -> Engine:
        """Build the process engine; its QueuePool is opened lazily."""
        url = make_url(self.url).set(drivername="postgresql+psycopg")
        return create_engine(
            url,
            connect_args=self.connection_kwargs(),
            pool_size=self.max_size,
            max_overflow=0,
            pool_timeout=5,
            pool_pre_ping=True,
        )

    def connection_kwargs(self) -> dict[str, object]:
        # Keep prepared statements disabled across local and hosted pool modes.
        kwargs: dict[str, object] = {
            "prepare_threshold": None,
            "connect_timeout": 5,
        }
        if urlsplit(self.url).hostname not in {"127.0.0.1", "localhost", "::1"}:
            kwargs["sslrootcert"] = str(
                files("gg.runtime").joinpath("certs/supabase-prod-ca-2021.crt")
            )
        return kwargs
