import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dsg_spacetime.console import create_console_server
from dsg_spacetime.licensing import generate_signing_key, issue_entitlement


def build_runtime_files(tmp_path):
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "import json,sys\np=json.load(sys.stdin)\njson.dump({'ok':True},sys.stdout)\n",
        encoding="utf-8",
    )
    key = tmp_path / "seller.pem"
    public_key = generate_signing_key(str(key))
    now = datetime.now(timezone.utc)
    entitlement = issue_entitlement(
        private_key_path=str(key),
        entitlement_id="ent-console-security",
        customer_id="customer-console-security",
        deployment_id="deployment-console-security",
        allowed_routes=["route.ai-echo"],
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
    )
    entitlement_path = tmp_path / "entitlement.json"
    entitlement_path.write_text(entitlement.model_dump_json(), encoding="utf-8")
    config_path = tmp_path / "deployment.json"
    config_path.write_text(
        json.dumps(
            {
                "deployment_id": "deployment-console-security",
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
        ),
        encoding="utf-8",
    )
    return config_path, entitlement_path, public_key


def test_console_blocks_host_rebinding_cross_origin_and_non_json_posts(tmp_path):
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
    message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode()
    try:
        hostile_origin = Request(
            f"{base}/api/mcp",
            data=message,
            headers={"Content-Type": "application/json", "Origin": "https://attacker.example"},
            method="POST",
        )
        try:
            urlopen(hostile_origin, timeout=5)
            raise AssertionError("hostile origin unexpectedly accepted")
        except HTTPError as error:
            assert error.code == 403
            assert json.loads(error.read().decode())["error"] == "CONSOLE_ORIGIN_BLOCKED"

        non_json = Request(
            f"{base}/api/mcp",
            data=message,
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        try:
            urlopen(non_json, timeout=5)
            raise AssertionError("non-JSON post unexpectedly accepted")
        except HTTPError as error:
            assert error.code == 415
            assert json.loads(error.read().decode())["error"] == "APPLICATION_JSON_REQUIRED"

        rebound_host = Request(f"{base}/api/status", headers={"Host": "attacker.example"})
        try:
            urlopen(rebound_host, timeout=5)
            raise AssertionError("non-loopback Host unexpectedly accepted")
        except HTTPError as error:
            assert error.code == 403
            assert json.loads(error.read().decode())["error"] == "CONSOLE_HOST_BLOCKED"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
