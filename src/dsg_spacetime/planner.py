from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .runtime import AgentIdentity, Plan, Route, SpacetimeRuntime


class RouteIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_node: str
    target_node: str
    capability: str


class AIPlanProposal(BaseModel):
    """Untrusted AI output. It is a proposal, never an authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(min_length=1, max_length=192)
    intent: str = Field(min_length=1, max_length=4000)
    participants: tuple[AgentIdentity, ...]
    routes: tuple[RouteIntent, ...]


class AIPlanner(Protocol):
    def propose(self, *, intent: str, public_nodes: list[dict[str, object]]) -> AIPlanProposal: ...


class Composer:
    """Turns untrusted AI proposals into deterministically validated Spacetime plans."""

    def __init__(self, runtime: SpacetimeRuntime):
        self.runtime = runtime

    def compose(self, proposal: AIPlanProposal) -> Plan:
        matched: list[Route] = []
        for requested in proposal.routes:
            candidates = [
                route
                for route in self.runtime.routes.values()
                if route.source_node == requested.source_node
                and route.target_node == requested.target_node
                and route.capability == requested.capability
            ]
            if len(candidates) != 1:
                raise PermissionError("AI_ROUTE_NOT_UNIQUELY_RESOLVABLE")
            matched.append(candidates[0])

        route_ids = tuple(route.route_id for route in matched)
        if len(route_ids) != len(set(route_ids)):
            raise PermissionError("AI_ROUTE_DUPLICATE")

        return Plan(
            plan_id=proposal.plan_id,
            intent=proposal.intent,
            participants=proposal.participants,
            route_ids=route_ids,
        )

    def discover_public_nodes(self) -> list[dict[str, object]]:
        return [
            {
                "node_id": node.node_id,
                "label": node.public_label,
                "capabilities": sorted(node.capabilities),
            }
            for node in sorted(self.runtime.nodes.values(), key=lambda item: item.node_id)
        ]
