"""Same-origin React serving, after all HTTP and WebSocket API routes."""

from ipaddress import ip_address
from pathlib import Path
from urllib.parse import unquote, urlsplit

from starlette.datastructures import Headers
from starlette.responses import FileResponse, JSONResponse


class OriginGuard:
    """Only the configured authority is accepted from the public proxy."""

    def __init__(self, app, origin: str, internal_proxy: bool = False):
        self.app = app
        self.authority = urlsplit(origin).netloc.lower()
        self.scheme = urlsplit(origin).scheme
        self.internal_proxy = internal_proxy

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"}:
            headers = Headers(scope=scope)
            forwarded = headers.get("x-forwarded-host")
            host = forwarded or headers.get("host", "")
            invalid = host.lower() != self.authority
            # Modal Servers replace Host with the private container address and
            # do not supply X-Forwarded-Host. Accept only that explicit transport;
            # callbacks still use settings.web_origin, never this internal Host.
            if invalid and self.internal_proxy and not forwarded:
                try:
                    parsed = urlsplit("http://" + host)
                    peer = scope.get("client")
                    invalid = not (
                        parsed.port == 8000
                        and ip_address(parsed.hostname).is_private
                        and peer
                        and ip_address(peer[0]).is_private
                    )
                except ValueError:
                    pass
            if headers.get("forwarded"):
                invalid = True  # Unsupported proxy dialect is rejected, never trusted.
            proto = headers.get("x-forwarded-proto")
            if proto and proto != self.scheme:
                invalid = True
            if invalid:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await JSONResponse({"detail": "invalid public origin"}, 400)(
                        scope, receive, send
                    )
                return
            # Canonicalize framework-generated redirects after validating transport.
            scope = dict(scope)
            scope["scheme"] = (
                self.scheme
                if scope["type"] == "http"
                else ("wss" if self.scheme == "https" else "ws")
            )
            scope["headers"] = [
                (key, value) for key, value in scope["headers"] if key != b"host"
            ] + [(b"host", self.authority.encode())]
        await self.app(scope, receive, send)


class StaticWeb:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        if not (self.directory / "index.html").is_file():
            raise ValueError("React build index.html is missing")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        path = unquote(scope["path"]).lstrip("/")
        parts = path.split("/")
        reserved = parts[0] in {
            "tasks",
            "api",
            "auth",
            "webhooks",
            "health",
            "ready",
            "docs",
            "openapi.json",
            "redoc",
        }
        invalid = (
            any(p.startswith(".") for p in parts) or "\\" in path or "\x00" in path
        )
        target = (self.directory / path).resolve()
        if (
            reserved
            or invalid
            or not target.is_relative_to(self.directory)
            or scope["method"] not in {"GET", "HEAD"}
        ):
            response = JSONResponse({"detail": "Not Found"}, 404)
        elif target.is_file():
            cache = "no-store" if target.name == "index.html" else "no-cache"
            response = FileResponse(target, headers={"Cache-Control": cache})
        elif parts[0] == "assets" or Path(path).suffix:
            response = JSONResponse({"detail": "Not Found"}, 404)
        else:
            response = FileResponse(
                self.directory / "index.html", headers={"Cache-Control": "no-store"}
            )
        await response(scope, receive, send)
