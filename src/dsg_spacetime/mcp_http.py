from __future__ import annotations

import hmac
import ipaddress
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .mcp_stdio import MAX_MESSAGE_BYTES, PROTOCOL_VERSION, StdioMcpServer, load_runtime


MCP_PATH = "/mcp"
HEALTH_PATH = "/health"
DEFAULT_API_KEY_ENV = "DSG_SPACETIME_API_KEY"


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _resolve_api_key(host: str, env_name: str) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    if not _is_loopback_host(host):
        raise RuntimeError("HTTP_API_KEY_REQUIRED_FOR_NON_LOOPBACK_BIND")
    return None


class HttpMcpApplication:
    def __init__(
        self,
        server: StdioMcpServer,
        *,
        api_key: str | None = None,
        allowed_origins: tuple[str, ...] = (),
    ) -> None:
        self.server = server
        self.api_key = api_key
        self.allowed_origins = frozenset(allowed_origins)

    def origin_allowed(self, origin: str | None) -> bool:
        if origin is None:
            return True
        return origin in self.allowed_origins

    def authorized(self, authorization: str | None) -> bool:
        if self.api_key is None:
            return True
        if authorization is None or not authorization.startswith("Bearer "):
            return False
        token = authorization.removeprefix("Bearer ")
        return hmac.compare_digest(token, self.api_key)


def _make_handler(app: HttpMcpApplication) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "DSGSpacetimeMCP/0.1"
        protocol_version = "HTTP/1.1"

        def _cors_headers(self) -> dict[str, str]:
            origin = self.headers.get("Origin")
            if origin and app.origin_allowed(origin):
                return {
                    "Access-Control-Allow-Origin": origin,
                    "Vary": "Origin",
                }
            return {}

        def _send_json(
            self,
            status: int,
            payload: dict[str, Any],
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in self._cors_headers().items():
                self.send_header(name, value)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_empty(self, status: int, *, headers: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            for name, value in self._cors_headers().items():
                self.send_header(name, value)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()

        def _guard_mcp(self) -> bool:
            origin = self.headers.get("Origin")
            if not app.origin_allowed(origin):
                self._send_json(403, {"error": "ORIGIN_NOT_ALLOWED"})
                return False
            if not app.authorized(self.headers.get("Authorization")):
                self._send_json(
                    401,
                    {"error": "UNAUTHORIZED"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
                return False
            return True

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == HEALTH_PATH:
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "service": "dsg-spacetime-mcp",
                        "transport": "streamable-http",
                        "protocolVersion": PROTOCOL_VERSION,
                    },
                )
                return
            if path == MCP_PATH:
                if not self._guard_mcp():
                    return
                self._send_json(
                    405,
                    {"error": "SSE_STREAM_NOT_ENABLED"},
                    headers={"Allow": "POST, OPTIONS"},
                )
                return
            self._send_json(404, {"error": "NOT_FOUND"})

        def do_OPTIONS(self) -> None:
            path = urlsplit(self.path).path
            if path != MCP_PATH:
                self._send_empty(404)
                return
            origin = self.headers.get("Origin")
            if not app.origin_allowed(origin):
                self._send_json(403, {"error": "ORIGIN_NOT_ALLOWED"})
                return
            headers = {
                "Allow": "POST, OPTIONS",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, MCP-Protocol-Version",
            }
            self._send_empty(204, headers=headers)

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if path != MCP_PATH:
                self._send_json(404, {"error": "NOT_FOUND"})
                return
            if not self._guard_mcp():
                return

            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._send_json(415, {"error": "CONTENT_TYPE_MUST_BE_APPLICATION_JSON"})
                return

            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._send_json(411, {"error": "CONTENT_LENGTH_REQUIRED"})
                return
            try:
                content_length = int(raw_length)
            except ValueError:
                self._send_json(400, {"error": "INVALID_CONTENT_LENGTH"})
                return
            if content_length < 0 or content_length > MAX_MESSAGE_BYTES:
                self._send_json(413, {"error": "REQUEST_TOO_LARGE"})
                return

            raw = self.rfile.read(content_length)
            try:
                message = json.loads(raw.decode("utf-8"))
                if not isinstance(message, dict):
                    raise ValueError("message must be object")
            except Exception:
                self._send_json(
                    400,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    },
                )
                return

            response = app.server.handle(message)
            if response is None:
                self._send_empty(202)
                return
            self._send_json(200, response)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def make_http_server(
    server: StdioMcpServer,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    api_key: str | None = None,
    allowed_origins: tuple[str, ...] = (),
) -> ThreadingHTTPServer:
    app = HttpMcpApplication(
        server,
        api_key=api_key,
        allowed_origins=allowed_origins,
    )
    return ThreadingHTTPServer((host, port), _make_handler(app))


def serve_http(
    *,
    config_path: str,
    entitlement_path: str,
    evidence_path: str,
    host: str = "127.0.0.1",
    port: int = 8787,
    api_key_env: str = DEFAULT_API_KEY_ENV,
    allowed_origins: tuple[str, ...] = (),
    public_key_b64: str | None = None,
) -> int:
    api_key = _resolve_api_key(host, api_key_env)
    runtime, composer, evidence = load_runtime(
        config_path=config_path,
        entitlement_path=entitlement_path,
        public_key_b64=public_key_b64,
        evidence_path=evidence_path,
    )
    mcp = StdioMcpServer(runtime, composer, evidence)
    httpd = make_http_server(
        mcp,
        host=host,
        port=port,
        api_key=api_key,
        allowed_origins=allowed_origins,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
