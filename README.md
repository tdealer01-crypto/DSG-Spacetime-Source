# DSG Spacetime — Public Source

Status: **PUBLISHED**

**DSG Spacetime is a customer-hosted governance backend for existing AI infrastructure.** Add governed execution, plan-bound authorization, offline entitlement verification, and tamper-evident evidence without migrating your existing agents, APIs, databases, cloud services, or automation stack.

Spacetime is designed to sit inside the customer's existing architecture as an execution boundary. Existing systems remain where they are; governed actions are routed through Spacetime before reaching customer-owned adapters and external services.

```text
Existing Agent / MCP / Automation
              │
              ▼
       DSG Spacetime
  ┌──────────────────────┐
  │ Plan binding         │
  │ Route authorization  │
  │ Agent binding        │
  │ Approval gate        │
  │ Entitlement check    │
  │ Evidence chain       │
  └──────────────────────┘
              │
              ▼
     Existing Adapter
              │
              ▼
 GitHub / Azure / Database /
 Stripe / Browser / Internal API
```

## Why Spacetime

Most teams already have agents, APIs, databases, CI/CD, cloud infrastructure, and automation in production. Replacing that stack just to add governance creates migration cost and operational risk.

Spacetime takes the opposite approach:

- **Keep your existing infrastructure.** Add governance around the execution path instead of rebuilding the system.
- **Run inside the customer's environment.** Core execution does not require a central DSG runtime service.
- **Bind execution to an explicit plan.** Actions are authorized against a concrete plan hash and registered Route.
- **Fail closed.** Missing plans, mismatched hashes, unauthorized Routes, invalid entitlements, unbound agents, and required approvals stop execution.
- **Use offline commercial entitlements.** Signed Ed25519 entitlements can be verified locally at runtime.
- **Keep evidence with the customer.** Successful governed executions produce local tamper-evident evidence records linked by hash.
- **Connect existing tools through adapters.** Customer-owned executables remain responsible for the actual integration with GitHub, cloud APIs, databases, browsers, internal services, or other systems.
- **Expose the same runtime through MCP and a local operational console.** Agents and operators can use the same governed execution core without moving the underlying systems.

## Add governance without migrating the system

Spacetime is not a replacement for the customer's agent framework, database, cloud account, API layer, or automation platform.

Before:

```text
Agent ───────────────→ Existing API / Tool
```

With Spacetime:

```text
Agent
  │
  ▼
DSG Spacetime
  │
  ├─ verify entitlement
  ├─ verify plan + plan hash
  ├─ verify Route
  ├─ verify agent binding
  ├─ require approval when configured
  │
  ▼
Existing Adapter
  │
  ▼
Existing API / Tool
  │
  ▼
Evidence
```

For Spacetime to act as an enforcement boundary, governed actions must be routed through Spacetime rather than retaining an unrestricted direct execution path around it.

## Runtime model

Spacetime composes and executes node-to-node AI workflows through registered Nodes and Routes.

AI-generated plan proposals are treated as untrusted input. A proposal must resolve to customer-registered Routes before it can become a bound Spacetime Plan. Execution is then checked against the bound plan, plan hash, Route scope, entitlement, agent identity, and any configured approval requirement before an adapter is called.

The runtime currently exposes these MCP capabilities:

```text
spacetime_discover
spacetime_compose
spacetime_execute
spacetime_verify_evidence
```

The product objective is simple:

> **Add a governed execution layer to infrastructure you already own, without forcing a platform migration.**

## Customer-owned trust boundary

DSG Spacetime is intended for customer-hosted deployment. Runtime configuration, entitlement verification, Route registration, adapter execution, and evidence storage can remain inside the customer's environment.

This makes Spacetime suitable for architectures where teams need stronger control over execution locality, data movement, and operational ownership than a centralized governance service alone can provide.

## Publication boundary

This repository contains the reviewed runtime implementation and non-commerce tests from the audited production snapshot `e8b27cad7136ac65bd6916f27cc3a6e65786ab36`.

It intentionally does **not** contain seller signing material, seller trust-root injection tooling, Stripe/Resend fulfillment, customer or transaction records, private commercial packaging, private release workflows, commercial runtime artifacts, or internal operator/continuity records.

## Source versus commercial binary

The source tree is inspectable and runnable as Python source. It supports caller-selected trust roots in source/library paths used by tests and development. Do not treat this source distribution as technically equivalent to the seller-trust-root-locked compiled commercial binary.

Commercial builds may inject a seller trust root and apply separate private build, signing, packaging, and anti-bypass verification outside this repository.

## Usage under license

Python 3.11+ is required for evaluation and development where separately authorized by the rights holder.

```bash
python -m pip install -e '.[dev]'
pytest -q
```

CLI entry point:

```bash
dsg-spacetime --help
```

## License

This repository is **Proprietary / all rights reserved** under the `DSG SPACETIME PROPRIETARY SOURCE-VISIBLE LICENSE` included as `LICENSE`.

Public visibility is provided for inspection and evaluation only under those terms. It is **not** an open-source license and does not grant a general right to use, modify, redistribute, sublicense, commercialize, or create derivative works from the source.

This repository was created as a clean-history publication from an audited source candidate. Private production repository history and private commercial operations were not transferred.
