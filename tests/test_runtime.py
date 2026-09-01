import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from datetime import datetime, timedelta, timezone

from dsg_spacetime import (
    AIPlanProposal,
    AgentIdentity,
    Composer,
    Entitlement,
    LicenseVerifier,
    Node,
    Plan,
    Route,
    RouteIntent,
    SpacetimeRuntime,
)
from dsg_spacetime.runtime import ExecutionRequest, _canonical


def make_runtime(*, licensed_routes=("route.ai-github.write",), route_limit=None):
    private_key = Ed25519PrivateKey.generate()
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    now = datetime.now(timezone.utc)
    unsigned = Entitlement(
        entitlement_id="ent-1",
        customer_id="customer-1",
        deployment_id="deployment-1",
        allowed_routes=tuple(licensed_routes),
        route_limit=route_limit,
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=30),
        signature_b64="",
    )
    signature = private_key.sign(_canonical(unsigned.unsigned_payload()))
    entitlement = unsigned.model_copy(
        update={"signature_b64": base64.b64encode(signature).decode("ascii")}
    )
    verifier = LicenseVerifier(base64.b64encode(public_raw).decode("ascii"))
    runtime = SpacetimeRuntime(
        deployment_id="deployment-1",
        license_verifier=verifier,
        entitlement=entitlement,
    )
    runtime.register_node(
        Node(
            node_id="node.ai",
            provider="customer-ai",
            public_label="AI Builder",
            capabilities=frozenset({"plan"}),
        )
    )
    runtime.register_node(
        Node(
            node_id="node.github",
            provider="github",
            public_label="GitHub",
            capabilities=frozenset({"source.write", "source.read"}),
        )
    )
    runtime.register_route(
        Route(
            route_id="route.ai-github.write",
            source_node="node.ai",
            target_node="node.github",
            capability="source.write",
            risk="medium",
        ),
        lambda payload: {"ok": True, "commit": payload["commit"]},
    )
    return runtime


def test_ai_composes_and_executes_licensed_route():
    runtime = make_runtime()
    agent = AgentIdentity(agent_id="agent-builder", principal="customer:builder")
    proposal = AIPlanProposal(
        plan_id="plan-1",
        intent="create and commit the application",
        participants=(agent,),
        routes=(
            RouteIntent(
                source_node="node.ai",
                target_node="node.github",
                capability="source.write",
            ),
        ),
    )
    plan = Composer(runtime).compose(proposal)
    plan_hash = runtime.bind_plan(plan)
    decision, result, evidence = runtime.execute(
        ExecutionRequest(
            plan_id=plan.plan_id,
            plan_hash=plan_hash,
            route_id="route.ai-github.write",
            agent=agent,
            payload={"commit": "abc123", "secret": "never persisted in evidence"},
        )
    )
    assert decision.verdict == "ALLOW"
    assert result == {"ok": True, "commit": "abc123"}
    assert evidence is not None
    assert runtime.verify_evidence_chain() is True
    assert "never persisted" not in evidence.model_dump_json()


def test_unlicensed_route_fails_closed():
    runtime = make_runtime(licensed_routes=())
    agent = AgentIdentity(agent_id="agent-builder", principal="customer:builder")
    plan = Plan(
        plan_id="plan-2",
        intent="write source",
        participants=(agent,),
        route_ids=("route.ai-github.write",),
    )
    plan_hash = runtime.bind_plan(plan)
    decision, result, evidence = runtime.execute(
        ExecutionRequest(
            plan_id=plan.plan_id,
            plan_hash=plan_hash,
            route_id="route.ai-github.write",
            agent=agent,
            payload={"commit": "blocked"},
        )
    )
    assert decision.verdict == "BLOCK"
    assert result is None
    assert evidence is None


def test_capacity_entitlement_blocks_route_registration_over_limit():
    runtime = make_runtime(licensed_routes=(), route_limit=1)
    with pytest.raises(PermissionError, match="ROUTE_LIMIT_EXCEEDED"):
        runtime.register_route(
            Route(
                route_id="route.ai-github.read",
                source_node="node.ai",
                target_node="node.github",
                capability="source.read",
                risk="low",
            ),
            lambda payload: {"ok": True},
        )


def test_capacity_entitlement_allows_execution_within_limit():
    runtime = make_runtime(licensed_routes=(), route_limit=1)
    agent = AgentIdentity(agent_id="agent-builder", principal="customer:builder")
    plan = Plan(
        plan_id="plan-capacity",
        intent="write source",
        participants=(agent,),
        route_ids=("route.ai-github.write",),
    )
    plan_hash = runtime.bind_plan(plan)
    decision, result, evidence = runtime.execute(
        ExecutionRequest(
            plan_id=plan.plan_id,
            plan_hash=plan_hash,
            route_id="route.ai-github.write",
            agent=agent,
            payload={"commit": "capacity-ok"},
        )
    )
    assert decision.verdict == "ALLOW"
    assert result == {"ok": True, "commit": "capacity-ok"}
    assert evidence is not None


def test_agent_not_bound_to_plan_fails_closed():
    runtime = make_runtime()
    owner = AgentIdentity(agent_id="agent-owner", principal="customer:owner")
    intruder = AgentIdentity(agent_id="agent-other", principal="customer:other")
    plan = Plan(
        plan_id="plan-3",
        intent="write source",
        participants=(owner,),
        route_ids=("route.ai-github.write",),
    )
    plan_hash = runtime.bind_plan(plan)
    decision = runtime.authorize(
        ExecutionRequest(
            plan_id=plan.plan_id,
            plan_hash=plan_hash,
            route_id="route.ai-github.write",
            agent=intruder,
            payload={"commit": "x"},
        )
    )
    assert decision.verdict == "BLOCK"


def test_unknown_ai_route_is_rejected_before_plan_binding():
    runtime = make_runtime()
    agent = AgentIdentity(agent_id="agent-builder", principal="customer:builder")
    proposal = AIPlanProposal(
        plan_id="plan-4",
        intent="delete production",
        participants=(agent,),
        routes=(
            RouteIntent(
                source_node="node.ai",
                target_node="node.github",
                capability="production.delete",
            ),
        ),
    )
    with pytest.raises(PermissionError, match="AI_ROUTE_NOT_UNIQUELY_RESOLVABLE"):
        Composer(runtime).compose(proposal)


def test_evidence_tampering_is_detected():
    runtime = make_runtime()
    agent = AgentIdentity(agent_id="agent-builder", principal="customer:builder")
    plan = Plan(
        plan_id="plan-5",
        intent="write source",
        participants=(agent,),
        route_ids=("route.ai-github.write",),
    )
    plan_hash = runtime.bind_plan(plan)
    _, _, evidence = runtime.execute(
        ExecutionRequest(
            plan_id=plan.plan_id,
            plan_hash=plan_hash,
            route_id="route.ai-github.write",
            agent=agent,
            payload={"commit": "abc"},
        )
    )
    assert evidence is not None
    runtime.evidence.records[0] = evidence.model_copy(update={"result_hash": "tampered"})
    assert runtime.verify_evidence_chain() is False
