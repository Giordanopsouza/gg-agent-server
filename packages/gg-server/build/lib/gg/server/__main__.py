"""CLI entry: ``python -m gg.server``."""
from __future__ import annotations

import argparse

import uvicorn

from gg.server.app import create_app
from gg.server.config import DEFAULT_HOST, DEFAULT_PORT, get_settings


_WILDCARD_HOSTS = frozenset({"0.0.0.0", "::", "[::]"})


def resolve_bind_host(host: str | None, *, session_api_keys: list[str]) -> str:
    """Pick the socket bind address.

    When the operator omits ``--host``, we default to loopback unless session
    API keys are configured (task 010 will enforce them on ``/api/*``).
    """
    if host is not None:
        return host
    if session_api_keys:
        return "0.0.0.0"
    return DEFAULT_HOST


def main() -> None:
    parser = argparse.ArgumentParser(description="gg-agent-server")
    parser.add_argument(
        "--host",
        default=None,
        help=(
            "Host to bind to. Defaults to 127.0.0.1 when no session API keys "
            "are configured, or 0.0.0.0 when GG_SESSION_API_KEYS is set."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Port to bind to (default: {DEFAULT_PORT} or GG_PORT).",
    )
    args = parser.parse_args()

    settings = get_settings()
    host = resolve_bind_host(args.host, session_api_keys=settings.session_api_keys)
    port = args.port if args.port is not None else settings.port

    if host in _WILDCARD_HOSTS and not settings.session_api_keys:
        print(
            f"Warning: binding to {host} without session API keys exposes an "
            "unauthenticated server to the network."
        )

    app = create_app(settings)
    print(f"Starting gg-agent-server on {host}:{port}")
    print(f"Health check: http://{host}:{port}/health")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
