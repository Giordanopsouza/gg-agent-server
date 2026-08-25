"""CLI entry: ``python -m gg.runtime``."""
from __future__ import annotations

import argparse

import uvicorn

from gg.runtime.app import create_app
from gg.runtime.config import load_settings


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="gg fake runtime API")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    args = parser.parse_args()

    print(f"Starting gg-runtime on {args.host}:{args.port}")
    uvicorn.run(create_app(settings), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
