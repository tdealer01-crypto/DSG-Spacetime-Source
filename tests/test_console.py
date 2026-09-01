import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from dsg_spacetime.console import CONSOLE_HTML, create_console_server
from dsg_spacetime.licensing import generate_signing_key, issue_entitlement


def build_runtime_files(tmp_path, *, config_deployment_id="deployment-console"):
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
        entitlement_id="ent-console",
        customer_id="customer-console",
        deployment_id="deployment-console",
        allowed_routes=["route.ai-echo"],
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
    )
    entitlement_path = tmp_path / "entitlement.json"
    entitlement_path.write_text(entitlement.model_dump_json(indent=2), encoding="utf-8")
    config = {
        "deployment_id": config_deployment_id,
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


def request_json(url, payload=None):
    if payload is None:
        request = Request(url, headers={"Accept": "application/json"})
    else:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def rpc(base, request_id, method, params=None):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    status, response = request_json(f"{base}/api/mcp", message)
    assert status == 200
    assert response["id"] == request_id
    assert "error" not in response
    return response["result"]


def test_console_html_is_real_operational_surface():
    assert "DSG ONE · Spacetime Console" in CONSOLE_HTML
    assert "Run All Flows" in CONSOLE_HTML
    assert "spacetime_discover" in CONSOLE_HTML
    assert "spacetime_compose" in CONSOLE_HTML
    assert "spacetime_execute" in CONSOLE_HTML
    assert "spacetime_verify_evidence" in CONSOLE_HTML


def test_console_refuses_non_loopback_bind_before_loading_runtime():
    with pytest.raises(ValueError, match="CONSOLE_HOST_MUST_BE_LOOPBACK"):
        create_console_server(
            config_path="missing",
            entitlement_path="missing",
            evidence_path="missing",
            host="0.0.0.0",
            port=8765,
        )


def test_console_http_bridge_runs_real_mcp_flow_and_durable_evidence(tmp_path):
    config_path, entitlement_path, public_key = build_runtime_files(tmp_path)
    evidence_path = tmp_path / "console-evidence.jsonl"
    server = create_console_server(
        config_path=str(config_path),
        entitlement_path=str(entitlement_path),
        evidence_path=str(evidence_path),
        host="127.0.0.1",
        port=0,
        public_key_b64=public_key,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(f"{base}/", timeout=5) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert "Run All Flows" in html
            assert response.headers["Cache-Control"] == "no-store"

        status_code, status = request_json(f"{base}/api/status")
        assert status_code == 200
        assert status == {
            "status": "READY",
            "server": "dsg-spacetime",
            "protocol_version": "2025-06-18",
            "deployment_id": "deployment-console",
        }

        _, catalog = request_json(f"{base}/api/catalog")
        assert catalog["nodes"][1]["node_id"] == "node.echo"
        assert catalog["routes"] == [
            {
                "route_id": "route.ai-echo",
                "source_node": "node.ai",
                "target_node": "node.echo",
                "capability": "echo",
                "risk": "low",
                "approval_required": False,
            }
        ]

        initialized = rpc(base, 1, "initialize", {})
        assert initialized["protocolVersion"] == "2025-06-18"
        tools = rpc(base, 2, "tools/list", {})
        assert {item["name"] for item in tools["tools"]} == {
            "spacetime_discover",
            "spacetime_compose",
            "spacetime_execute",
            "spacetime_verify_evidence",
        }

        discovered = rpc(
            base,
            3,
            "tools/call",
            {"name": "spacetime_discover", "arguments": {"capabilities": ["echo"]}},
        )["structuredContent"]
        assert discovered["nodes"][0]["node_id"] == "node.echo"

        composed = rpc(
            base,
            4,
            "tools/call",
            {
                "name": "spacetime_compose",
                "arguments": {
                    "plan_id": "console-plan-1",
                    "intent": "echo through the selected governed Route",
                    "participants": [{"agent_id": "console-agent", "principal": "customer:operator"}],
                    "routes": [
                        {
                            "source_node": "node.ai",
                            "target_node": "node.echo",
                            "capability": "echo",
                        }
                    ],
                },
            },
        )["structuredContent"]
        assert composed["verdict"] == "BOUND"

        executed = rpc(
            base,
            5,
            "tools/call",
            {
                "name": "spacetime_execute",
                "arguments": {
                    "plan_id": "console-plan-1",
                    "plan_hash": composed["plan_hash"],
                    "route_id": "route.ai-echo",
                    "agent": {"agent_id": "console-agent", "principal": "customer:operator"},
                    "payload": {"value": "hello-console", "secret": "console-secret-must-not-persist"},
                },
            },
        )["structuredContent"]
        assert executed["decision"]["verdict"] == "ALLOW"
        assert executed["result"] == {"ok": True, "echo": "hello-console"}

        verified = rpc(
            base,
            6,
            "tools/call",
            {"name": "spacetime_verify_evidence", "arguments": {}},
        )["structuredContent"]
        assert verified == {"valid": True, "records": 1}
        assert "console-secret-must-not-persist" not in evidence_path.read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_console_still_fails_closed_on_wrong_deployment_entitlement(tmp_path):
    config_path, entitlement_path, public_key = build_runtime_files(
        tmp_path, config_deployment_id="deployment-wrong"
    )
    with pytest.raises(PermissionError, match="ENTITLEMENT_DEPLOYMENT_MISMATCH"):
        create_console_server(
            config_path=str(config_path),
            entitlement_path=str(entitlement_path),
            evidence_path=str(tmp_path / "evidence.jsonl"),
            host="127.0.0.1",
            port=0,
            public_key_b64=public_key,
        )


def test_console_rejects_malformed_json(tmp_path):
    config_path, entitlement_path, public_key = build_runtime_files(tmp_path)
    server = create_console_server(
        config_path=str(config_path),
        entitlement_path=str(entitlement_path),
        evidence_path=str(tmp_path / "evidence.jsonl"),
        host="127.0.0.1",
        port=0,
        public_key_b64=public_key,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        request = Request(
            f"{base}/api/mcp",
            data=b"not-json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as caught:
            urlopen(request, timeout=5)
        assert caught.value.code == 400
        body = json.loads(caught.value.read().decode("utf-8"))
        assert body["error"]["code"] == -32700
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
