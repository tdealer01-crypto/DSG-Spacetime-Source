from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .planner import AIPlanProposal, Composer
from .runtime import (
    Entitlement,
    ExecutionRequest,
    LicenseVerifier,
    Node,
    Route,
    SpacetimeRuntime,
)
from .storage import JsonlEvidenceChain
from .trust import get_builtin_license_public_key


PROTOCOL_VERSION = "2025-06-18"
MAX_MESSAGE_BYTES = 2_000_000
MAX_ADAPTER_OUTPUT_BYTES = 1_000_000


class AdapterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: tuple[str, ...] = Field(min_length=1)
    timeout_seconds: float = Field(default=60.0, gt=0.0, le=300.0)
    env_allowlist: tuple[str, ...] = ()

    @field_validator("command")
    @classmethod
    def require_absolute_executable(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or not Path(value[0]).is_absolute():
            raise ValueError("ADAPTER_EXECUTABLE_MUST_BE_ABSOLUTE")
        if any(not item for item in value):
            raise ValueError("ADAPTER_COMMAND_EMPTY_ARGUMENT")
        return value


class RouteBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route: Route
    adapter: AdapterConfig


class DeploymentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    deployment_id: str = Field(min_length=1, max_length=192)
    nodes: tuple[Node, ...]
    routes: tuple[RouteBinding, ...]


class ExecutableAdapter:
    """Calls a fixed customer/marketplace adapter executable without a shell."""

    def __init__(self, config: AdapterConfig):
        self.config = config

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
        for name in self.config.env_allowlist:
            if name in os.environ:
                env[name] = os.environ[name]

        completed = subprocess.run(
            list(self.config.command),
            input=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            capture_output=True,
            text=True,
            shell=False,
            timeout=self.config.timeout_seconds,
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("ADAPTER_EXECUTION_FAILED")
        if len(completed.stdout.encode("utf-8")) > MAX_ADAPTER_OUTPUT_BYTES:
            raise RuntimeError("ADAPTER_OUTPUT_TOO_LARGE")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("ADAPTER_OUTPUT_INVALID_JSON") from exc
        if not isinstance(result, dict):
            raise RuntimeError("ADAPTER_OUTPUT_MUST_BE_OBJECT")
        return result


def load_runtime(
    *,
    config_path: str,
    entitlement_path: str,
    evidence_path: str,
    public_key_b64: str | None = None,
) -> tuple[SpacetimeRuntime, Composer, JsonlEvidenceChain]:
    config = DeploymentConfig.model_validate_json(Path(config_path).read_text(encoding="utf-8"))
    entitlement = Entitlement.model_validate_json(
        Path(entitlement_path).read_text(encoding="utf-8")
    )
    trust_root = public_key_b64 if public_key_b64 is not None else get_builtin_license_public_key()
    verifier = LicenseVerifier(trust_root)
    verifier.verify(entitlement, deployment_id=config.deployment_id)

    runtime = SpacetimeRuntime(
        deployment_id=config.deployment_id,
        license_verifier=verifier,
        entitlement=entitlement,
    )
    evidence = JsonlEvidenceChain(evidence_path)
    evidence.ensure_ready()
    runtime.evidence = evidence

    for node in config.nodes:
        runtime.register_node(node)
    for binding in config.routes:
        runtime.register_route(binding.route, ExecutableAdapter(binding.adapter))

    return runtime, Composer(runtime), evidence


def _tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
    }
    if is_error:
        result["isError"] = True
    return result


def _tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "spacetime_discover",
            "description": "Discover customer-approved DSG Spacetime Nodes by capability.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "capabilities": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["capabilities"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True},
        },
        {
            "name": "spacetime_compose",
            "description": "Validate an untrusted AI N2N proposal and bind it as a Spacetime plan.",
            "inputSchema": AIPlanProposal.model_json_schema(),
            "annotations": {"readOnlyHint": False},
        },
        {
            "name": "spacetime_execute",
            "description": "Execute one licensed, plan-bound N2N Route through a customer-owned adapter.",
            "inputSchema": ExecutionRequest.model_json_schema(),
            "annotations": {"readOnlyHint": False, "destructiveHint": True},
        },
        {
            "name": "spacetime_verify_evidence",
            "description": "Verify the local tamper-evident DSG Spacetime evidence chain.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True},
        },
    ]


class StdioMcpServer:
    def __init__(self, runtime: SpacetimeRuntime, composer: Composer, evidence: JsonlEvidenceChain):
        self.runtime = runtime
        self.composer = composer
        self.evidence = evidence

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "spacetime_discover":
            capabilities = arguments.get("capabilities")
            if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
                return _tool_result({"verdict": "BLOCK", "reason": "INVALID_CAPABILITIES"}, is_error=True)
            nodes = self.runtime.discover(capabilities)
            return _tool_result(
                {
                    "nodes": [
                        {
                            "node_id": node.node_id,
                            "label": node.public_label,
                            "capabilities": sorted(node.capabilities),
                        }
                        for node in nodes
                    ]
                }
            )

        if name == "spacetime_compose":
            try:
                proposal = AIPlanProposal.model_validate(arguments)
                plan = self.composer.compose(proposal)
                plan_hash = self.runtime.bind_plan(plan)
                return _tool_result(
                    {
                        "verdict": "BOUND",
                        "plan": plan.model_dump(mode="json"),
                        "plan_hash": plan_hash,
                    }
                )
            except PermissionError as exc:
                return _tool_result(
                    {"verdict": "BLOCK", "reason": str(exc).strip("'") or "PROPOSAL_REJECTED"},
                    is_error=True,
                )
            except Exception:
                return _tool_result(
                    {"verdict": "BLOCK", "reason": "PROPOSAL_REJECTED"},
                    is_error=True,
                )

        if name == "spacetime_execute":
            try:
                self.evidence.ensure_ready()
                request = ExecutionRequest.model_validate(arguments)
                decision, result, evidence = self.runtime.execute(request)
                payload = {
                    "decision": decision.model_dump(mode="json"),
                    "result": result,
                    "evidence": evidence.model_dump(mode="json") if evidence else None,
                }
                return _tool_result(payload, is_error=decision.verdict != "ALLOW")
            except Exception:
                return _tool_result(
                    {"verdict": "BLOCK", "reason": "EXECUTION_REJECTED"},
                    is_error=True,
                )

        if name == "spacetime_verify_evidence":
            valid = self.evidence.verify_chain() and self.runtime.verify_evidence_chain()
            return _tool_result({"valid": valid, "records": len(self.evidence.records)}, is_error=not valid)

        return _tool_result({"verdict": "BLOCK", "reason": "UNKNOWN_TOOL"}, is_error=True)

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        method = message.get("method")

        if method == "notifications/initialized":
            return None
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "dsg-spacetime", "version": "0.1.0"},
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": _tools()}}
        if method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32602, "message": "Invalid params"},
                }
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": self._call_tool(name, arguments),
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"},
        }


def serve_stdio(
    *,
    config_path: str,
    entitlement_path: str,
    evidence_path: str,
    public_key_b64: str | None = None,
) -> int:
    runtime, composer, evidence = load_runtime(
        config_path=config_path,
        entitlement_path=entitlement_path,
        public_key_b64=public_key_b64,
        evidence_path=evidence_path,
    )
    server = StdioMcpServer(runtime, composer, evidence)

    for raw_line in sys.stdin.buffer:
        if len(raw_line) > MAX_MESSAGE_BYTES:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Request too large"},
            }
        else:
            try:
                message = json.loads(raw_line.decode("utf-8"))
                if not isinstance(message, dict):
                    raise ValueError("message must be object")
                response = server.handle(message)
            except Exception:
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":"), ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0
