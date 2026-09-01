import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

from dsg_spacetime.licensing import generate_signing_key, issue_entitlement
from dsg_spacetime.mcp_stdio import PROTOCOL_VERSION, StdioMcpServer, load_runtime
from dsg_spacetime.storage import JsonlEvidenceChain


def build_runtime_files(tmp_path, *, config_deployment_id="deployment-a"):
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
        entitlement_id="ent-1",
        customer_id="customer-a",
        deployment_id="deployment-a",
        allowed_routes=["route.ai-echo"],
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=30),
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


def test_local_mcp_n2n_flow_and_durable_evidence(tmp_path):
    config_path, entitlement_path, public_key = build_runtime_files(tmp_path)
    evidence_path = tmp_path / "evidence.jsonl"
    runtime, composer, evidence = load_runtime(
        config_path=str(config_path),
        entitlement_path=str(entitlement_path),
        public_key_b64=public_key,
        evidence_path=str(evidence_path),
    )
    server = StdioMcpServer(runtime, composer, evidence)

    initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert initialized["result"]["protocolVersion"] == PROTOCOL_VERSION

    tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert names == {
        "spacetime_discover",
        "spacetime_compose",
        "spacetime_execute",
        "spacetime_verify_evidence",
    }

    discover = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "spacetime_discover", "arguments": {"capabilities": ["echo"]}},
        }
    )
    assert discover["result"]["structuredContent"]["nodes"][0]["node_id"] == "node.echo"

    compose = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "spacetime_compose",
                "arguments": {
                    "plan_id": "plan-1",
                    "intent": "echo a value",
                    "participants": [{"agent_id": "agent-1", "principal": "customer:agent"}],
                    "routes": [
                        {
                            "source_node": "node.ai",
                            "target_node": "node.echo",
                            "capability": "echo",
                        }
                    ],
                },
            },
        }
    )
    composed = compose["result"]["structuredContent"]
    assert composed["verdict"] == "BOUND"

    execute = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "spacetime_execute",
                "arguments": {
                    "plan_id": "plan-1",
                    "plan_hash": composed["plan_hash"],
                    "route_id": "route.ai-echo",
                    "agent": {"agent_id": "agent-1", "principal": "customer:agent"},
                    "payload": {"value": "hello", "secret": "not stored as plaintext evidence"},
                },
            },
        }
    )
    executed = execute["result"]["structuredContent"]
    assert executed["decision"]["verdict"] == "ALLOW"
    assert executed["result"] == {"ok": True, "echo": "hello"}
    assert evidence_path.exists()
    assert "not stored as plaintext" not in evidence_path.read_text(encoding="utf-8")

    reloaded = JsonlEvidenceChain(str(evidence_path))
    assert reloaded.verify_chain() is True
    assert len(reloaded.records) == 1


def test_license_cannot_be_reused_for_another_deployment(tmp_path):
    config_path, entitlement_path, public_key = build_runtime_files(
        tmp_path, config_deployment_id="deployment-b"
    )
    with pytest.raises(PermissionError, match="ENTITLEMENT_DEPLOYMENT_MISMATCH"):
        load_runtime(
            config_path=str(config_path),
            entitlement_path=str(entitlement_path),
            public_key_b64=public_key,
            evidence_path=str(tmp_path / "evidence.jsonl"),
        )
