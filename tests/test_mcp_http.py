import http.client
import json
import sys
import threading
from datetime import datetime, timedelta, timezone

import pytest

from dsg_spacetime.licensing import generate_signing_key, issue_entitlement
from dsg_spacetime.mcp_http import _resolve_api_key, make_http_server
from dsg_spacetime.mcp_stdio import PROTOCOL_VERSION, StdioMcpServer, load_runtime


def build_runtime_files(tmp_path):
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "import json,sys\np=json.load(sys.stdin)\njson.dump({'ok':True,'echo':p.get('value')},sys.stdout)\n",
        encoding="utf-8",
    )

    key = tmp_path / "seller.pem"
    public_key = generate_signing_key(str(key))
    now = datetime.now(timezone.utc)
    entitlement = issue_entitlement(
        private_key_path=str(key),
        entitlement_id="ent-http",
        customer_id="customer-http",
        deployment_id="deployment-http",
        allowed_routes=["route.ai-echo"],
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=30),
    )
    entitlement_path = tmp_path / "entitlement.json"
    entitlement_path.write_text(entitlement.model_dump_json(indent=2), encoding="utf-8")

    config = {
        "deployment_id": "deployment-http",
        "nodes": [
            {
                "node_id": "node.ai",
                "provider": "customer-ai",
                "capabilities": ["plan"],
                "public_label": "AI Builder",
            },
            {
                "node_id": "node.echo",
                "provider": "customer-adapter",
                "capabilities": ["echo"],
                "public_label": "Echo Node",
            },
        ],
        "routes": [
            {
                "route": {
                    "route_id": "route.ai-echo",
                    "source_node": "node.ai",
                    "target_node": "node.echo",
                    "capability": "echo",
                    "risk": "low",
                    "approval_required": False,
                },
                "adapter": {
                    "command": [sys.executable, str(adapter)],
                    "timeout_seconds": 10,
                    "env_allowlist": [],
                },
            }
        ],
    }
    config_path = tmp_path / "deployment.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path, entitlement_path, public_key


def build_mcp(tmp_path):
    config_path, entitlement_path, public_key = build_runtime_files(tmp_path)
    runtime, composer, evidence = load_runtime(
        config_path=str(config_path),
        entitlement_path=str(entitlement_path),
        public_key_b64=public_key,
        evidence_path=str(tmp_path / "evidence.jsonl"),
    )
    return StdioMcpServer(runtime, composer, evidence)


def start_server(mcp, *, api_key=None, allowed_origins=()):
    httpd = make_http_server(
        mcp,
        host="127.0.0.1",
        port=0,
        api_key=api_key,
        allowed_origins=allowed_origins,
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def request(httpd, method, path, *, payload=None, headers=None):
    host, port = httpd.server_address
    connection = http.client.HTTPConnection(host, port, timeout=3)
    body = None
    merged_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        merged_headers.setdefault("Content-Type", "application/json")
    connection.request(method, path, body=body, headers=merged_headers)
    response = connection.getresponse()
    raw = response.read()
    result = json.loads(raw.decode("utf-8")) if raw else None
    response_headers = dict(response.getheaders())
    status = response.status
    connection.close()
    return status, result, response_headers


def stop_server(httpd, thread):
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=3)


def test_http_health_initialize_and_tools_list(tmp_path):
    httpd, thread = start_server(build_mcp(tmp_path))
    try:
        status, health, _ = request(httpd, "GET", "/health")
        assert status == 200
        assert health == {
            "ok": True,
            "service": "dsg-spacetime-mcp",
            "transport": "streamable-http",
            "protocolVersion": PROTOCOL_VERSION,
        }

        status, initialized, _ = request(
            httpd,
            "POST",
            "/mcp",
            payload={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert status == 200
        assert initialized["result"]["protocolVersion"] == PROTOCOL_VERSION

        status, tools, _ = request(
            httpd,
            "POST",
            "/mcp",
            payload={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert status == 200
        assert {tool["name"] for tool in tools["result"]["tools"]} == {
            "spacetime_discover",
            "spacetime_compose",
            "spacetime_execute",
            "spacetime_verify_evidence",
        }
    finally:
        stop_server(httpd, thread)


def test_http_bearer_auth_is_enforced(tmp_path):
    httpd, thread = start_server(build_mcp(tmp_path), api_key="test-http-key")
    payload = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}
    try:
        status, body, headers = request(httpd, "POST", "/mcp", payload=payload)
        assert status == 401
        assert body == {"error": "UNAUTHORIZED"}
        assert headers["WWW-Authenticate"] == "Bearer"

        status, _, _ = request(
            httpd,
            "POST",
            "/mcp",
            payload=payload,
            headers={"Authorization": "Bearer wrong"},
        )
        assert status == 401

        status, body, _ = request(
            httpd,
            "POST",
            "/mcp",
            payload=payload,
            headers={"Authorization": "Bearer test-http-key"},
        )
        assert status == 200
        assert body["result"] == {}
    finally:
        stop_server(httpd, thread)


def test_browser_origin_is_fail_closed(tmp_path):
    httpd, thread = start_server(
        build_mcp(tmp_path),
        allowed_origins=("https://judge.example",),
    )
    payload = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}
    try:
        status, body, _ = request(
            httpd,
            "POST",
            "/mcp",
            payload=payload,
            headers={"Origin": "https://evil.example"},
        )
        assert status == 403
        assert body == {"error": "ORIGIN_NOT_ALLOWED"}

        status, body, headers = request(
            httpd,
            "POST",
            "/mcp",
            payload=payload,
            headers={"Origin": "https://judge.example"},
        )
        assert status == 200
        assert body["result"] == {}
        assert headers["Access-Control-Allow-Origin"] == "https://judge.example"
    finally:
        stop_server(httpd, thread)


def test_mcp_notification_returns_accepted(tmp_path):
    httpd, thread = start_server(build_mcp(tmp_path))
    try:
        status, body, _ = request(
            httpd,
            "POST",
            "/mcp",
            payload={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        assert status == 202
        assert body is None
    finally:
        stop_server(httpd, thread)


def test_non_loopback_bind_requires_api_key(monkeypatch):
    env_name = "DSG_SPACETIME_TEST_HTTP_KEY"
    monkeypatch.delenv(env_name, raising=False)
    assert _resolve_api_key("127.0.0.1", env_name) is None
    assert _resolve_api_key("localhost", env_name) is None
    with pytest.raises(RuntimeError, match="HTTP_API_KEY_REQUIRED_FOR_NON_LOOPBACK_BIND"):
        _resolve_api_key("0.0.0.0", env_name)

    monkeypatch.setenv(env_name, "remote-key")
    assert _resolve_api_key("0.0.0.0", env_name) == "remote-key"
