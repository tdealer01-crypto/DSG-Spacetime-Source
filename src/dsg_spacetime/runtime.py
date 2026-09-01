from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, field_validator


Risk = Literal["low", "medium", "high", "critical"]
Verdict = Literal["ALLOW", "BLOCK"]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=128)
    capabilities: frozenset[str]
    public_label: str = Field(min_length=1, max_length=128)

    @field_validator("capabilities")
    @classmethod
    def require_capability(cls, value: frozenset[str]) -> frozenset[str]:
        if not value:
            raise ValueError("node must expose at least one capability")
        return value


class Route(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route_id: str = Field(min_length=1, max_length=192)
    source_node: str
    target_node: str
    capability: str
    risk: Risk = "medium"
    approval_required: bool = False


class AgentIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1, max_length=160)
    principal: str = Field(min_length=1, max_length=256)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(min_length=1, max_length=192)
    intent: str = Field(min_length=1, max_length=4000)
    participants: tuple[AgentIdentity, ...]
    route_ids: tuple[str, ...]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("participants", "route_ids")
    @classmethod
    def require_nonempty(cls, value: tuple[Any, ...]) -> tuple[Any, ...]:
        if not value:
            raise ValueError("plan collection cannot be empty")
        return value

    @property
    def plan_hash(self) -> str:
        return _hash(self.model_dump(mode="json"))


class Entitlement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entitlement_id: str
    customer_id: str
    deployment_id: str
    allowed_routes: tuple[str, ...] = ()
    route_limit: int | None = Field(default=None, ge=1, le=100_000)
    not_before: datetime
    expires_at: datetime | None = None
    signature_b64: str

    def unsigned_payload(self) -> dict[str, Any]:
        # exclude_none preserves signature compatibility with legacy exact-route
        # entitlements issued before route_limit/perpetual fields existed.
        return self.model_dump(mode="json", exclude={"signature_b64"}, exclude_none=True)


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str
    plan_hash: str
    route_id: str
    agent: AgentIdentity
    payload: dict[str, Any]
    approval_id: str | None = None


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: Verdict
    reason: str
    plan_id: str
    route_id: str
    decision_hash: str


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int
    timestamp: datetime
    plan_id: str
    route_id: str
    agent_id: str
    decision_hash: str
    request_hash: str
    result_hash: str
    previous_hash: str | None
    evidence_hash: str


class LicenseVerifier:
    """Offline verification of DSG-issued commercial entitlements."""

    def __init__(self, public_key_b64: str):
        raw = base64.b64decode(public_key_b64, validate=True)
        self._key = Ed25519PublicKey.from_public_bytes(raw)

    def verify(self, entitlement: Entitlement, *, deployment_id: str, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if entitlement.deployment_id != deployment_id:
            raise PermissionError("ENTITLEMENT_DEPLOYMENT_MISMATCH")
        if bool(entitlement.allowed_routes) == (entitlement.route_limit is not None):
            raise PermissionError("ENTITLEMENT_SCOPE_INVALID")
        if now < entitlement.not_before:
            raise PermissionError("ENTITLEMENT_NOT_ACTIVE")
        if entitlement.expires_at is not None and now >= entitlement.expires_at:
            raise PermissionError("ENTITLEMENT_EXPIRED")
        try:
            signature = base64.b64decode(entitlement.signature_b64, validate=True)
            self._key.verify(signature, _canonical(entitlement.unsigned_payload()))
        except (ValueError, InvalidSignature) as exc:
            raise PermissionError("ENTITLEMENT_SIGNATURE_INVALID") from exc


Adapter = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class EvidenceChain:
    records: list[EvidenceRecord] = field(default_factory=list)

    def append(
        self,
        *,
        plan_id: str,
        route_id: str,
        agent_id: str,
        decision_hash: str,
        request_hash: str,
        result_hash: str,
    ) -> EvidenceRecord:
        previous_hash = self.records[-1].evidence_hash if self.records else None
        body = {
            "index": len(self.records),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "plan_id": plan_id,
            "route_id": route_id,
            "agent_id": agent_id,
            "decision_hash": decision_hash,
            "request_hash": request_hash,
            "result_hash": result_hash,
            "previous_hash": previous_hash,
        }
        record = EvidenceRecord(
            index=body["index"],
            timestamp=datetime.fromisoformat(body["timestamp"]),
            plan_id=plan_id,
            route_id=route_id,
            agent_id=agent_id,
            decision_hash=decision_hash,
            request_hash=request_hash,
            result_hash=result_hash,
            previous_hash=previous_hash,
            evidence_hash=_hash(body),
        )
        self.records.append(record)
        return record


class SpacetimeRuntime:
    """Customer-owned N2N runtime. No central DSG service is required."""

    def __init__(
        self,
        *,
        deployment_id: str,
        license_verifier: LicenseVerifier,
        entitlement: Entitlement,
    ) -> None:
        self.deployment_id = deployment_id
        self.license_verifier = license_verifier
        self.entitlement = entitlement
        self.nodes: dict[str, Node] = {}
        self.routes: dict[str, Route] = {}
        self.plans: dict[str, Plan] = {}
        self.adapters: dict[str, Adapter] = {}
        self.evidence = EvidenceChain()

    def register_node(self, node: Node) -> None:
        if node.node_id in self.nodes:
            raise ValueError("DUPLICATE_NODE")
        self.nodes[node.node_id] = node

    def register_route(self, route: Route, adapter: Adapter) -> None:
        if route.route_id in self.routes:
            raise ValueError("DUPLICATE_ROUTE")
        source = self.nodes.get(route.source_node)
        target = self.nodes.get(route.target_node)
        if source is None or target is None:
            raise ValueError("ROUTE_NODE_MISSING")
        if route.capability not in target.capabilities:
            raise ValueError("TARGET_CAPABILITY_MISMATCH")
        if not self.entitlement.allowed_routes and self.entitlement.route_limit is not None:
            if len(self.routes) >= self.entitlement.route_limit:
                raise PermissionError("ROUTE_LIMIT_EXCEEDED")
        self.routes[route.route_id] = route
        self.adapters[route.route_id] = adapter

    def bind_plan(self, plan: Plan) -> str:
        missing = [route_id for route_id in plan.route_ids if route_id not in self.routes]
        if missing:
            raise ValueError("PLAN_ROUTE_MISSING")
        if plan.plan_id in self.plans:
            raise ValueError("DUPLICATE_PLAN")
        self.plans[plan.plan_id] = plan
        return plan.plan_hash

    def discover(self, capabilities: Iterable[str]) -> list[Node]:
        requested = set(capabilities)
        return sorted(
            [node for node in self.nodes.values() if requested.intersection(node.capabilities)],
            key=lambda node: node.node_id,
        )

    def authorize(self, request: ExecutionRequest) -> Decision:
        reason = "ALLOW"
        verdict: Verdict = "ALLOW"
        try:
            self.license_verifier.verify(
                self.entitlement,
                deployment_id=self.deployment_id,
            )
            plan = self.plans.get(request.plan_id)
            if plan is None:
                raise PermissionError("PLAN_NOT_FOUND")
            if request.plan_hash != plan.plan_hash:
                raise PermissionError("PLAN_HASH_MISMATCH")
            if request.route_id not in plan.route_ids:
                raise PermissionError("ROUTE_OUTSIDE_PLAN")
            if self.entitlement.allowed_routes:
                if request.route_id not in self.entitlement.allowed_routes:
                    raise PermissionError("ROUTE_NOT_LICENSED")
            elif self.entitlement.route_limit is None:
                raise PermissionError("ENTITLEMENT_SCOPE_INVALID")
            participant_ids = {participant.agent_id for participant in plan.participants}
            if request.agent.agent_id not in participant_ids:
                raise PermissionError("AGENT_NOT_PLAN_BOUND")
            route = self.routes.get(request.route_id)
            if route is None:
                raise PermissionError("ROUTE_NOT_REGISTERED")
            if route.risk in {"high", "critical"} or route.approval_required:
                if not request.approval_id:
                    raise PermissionError("APPROVAL_REQUIRED")
        except Exception as exc:
            verdict = "BLOCK"
            reason = str(exc) or exc.__class__.__name__

        decision_body = {
            "verdict": verdict,
            "reason": reason,
            "plan_id": request.plan_id,
            "route_id": request.route_id,
            "agent_id": request.agent.agent_id,
            "request_hash": _hash(request.model_dump(mode="json", exclude={"payload"})),
        }
        return Decision(
            verdict=verdict,
            reason=reason,
            plan_id=request.plan_id,
            route_id=request.route_id,
            decision_hash=_hash(decision_body),
        )

    def execute(self, request: ExecutionRequest) -> tuple[Decision, dict[str, Any] | None, EvidenceRecord | None]:
        decision = self.authorize(request)
        if decision.verdict != "ALLOW":
            return decision, None, None

        adapter = self.adapters.get(request.route_id)
        if adapter is None:
            blocked = Decision(
                verdict="BLOCK",
                reason="ADAPTER_NOT_AVAILABLE",
                plan_id=request.plan_id,
                route_id=request.route_id,
                decision_hash=_hash({"previous": decision.decision_hash, "reason": "ADAPTER_NOT_AVAILABLE"}),
            )
            return blocked, None, None

        request_hash = _hash(request.payload)
        try:
            result = adapter(dict(request.payload))
            result_hash = _hash(result)
        except Exception as exc:
            blocked = Decision(
                verdict="BLOCK",
                reason=f"EXECUTION_FAILED:{exc.__class__.__name__}",
                plan_id=request.plan_id,
                route_id=request.route_id,
                decision_hash=_hash({"previous": decision.decision_hash, "reason": exc.__class__.__name__}),
            )
            return blocked, None, None

        record = self.evidence.append(
            plan_id=request.plan_id,
            route_id=request.route_id,
            agent_id=request.agent.agent_id,
            decision_hash=decision.decision_hash,
            request_hash=request_hash,
            result_hash=result_hash,
        )
        return decision, result, record

    def verify_evidence_chain(self) -> bool:
        previous: str | None = None
        for record in self.evidence.records:
            body = {
                "index": record.index,
                "timestamp": record.timestamp.isoformat(),
                "plan_id": record.plan_id,
                "route_id": record.route_id,
                "agent_id": record.agent_id,
                "decision_hash": record.decision_hash,
                "request_hash": record.request_hash,
                "result_hash": record.result_hash,
                "previous_hash": previous,
            }
            if record.previous_hash != previous or record.evidence_hash != _hash(body):
                return False
            previous = record.evidence_hash
        return True
