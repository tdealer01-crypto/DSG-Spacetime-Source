# DSG Spacetime — Public Source

Status: **PUBLISHED**  
Production verification snapshot: **5 September 2026**

**DSG Spacetime is a customer-hosted governance and execution boundary for existing AI infrastructure.** It adds plan-bound authorization, Route control, offline entitlement verification, provider/tool execution, and tamper-evident evidence without requiring customers to replace their existing agents, APIs, databases, cloud services, or automation stack.

The governing rule is:

> **Spacetime is the execution boundary. Approved work may continue through the authorized Route; out-of-plan or unsupported work must not bypass it.**

## Current architecture

```text
User
  ↓
Agent + Core Spin
  ↓
DSG Spacetime
  ↓ authorized Route
Agent provider / MCP provider / customer adapter
  ↓
DSG Spacetime evidence
  ↓
Agent + Core Spin
  ↓
User
```

`Agent + Core Spin` is the active job/session reasoning and history layer. `DSG Spacetime` is the authorization, execution, and evidence boundary. MCP and provider-native tools are capability transports behind that boundary.

There is no separate outer “gate” wrapped around Spacetime: **Spacetime itself performs the authorization decision before execution.**

## Core Spin and Spacetime storage stay separate

The two stores have different ownership and must not be collapsed into one ledger.

```text
Core Spin store                         Spacetime evidence store
───────────────                         ────────────────────────
job/session/history                     plan_id / route_id
provider refs                           decision_hash
usage / cost                            request_hash
workflow status                         result_hash
Spacetime receipt references            previous_hash
                                        evidence_hash
        │                                      │
        └──────── correlation references ──────┘
                          ↓
                    Unified read view
```

Core Spin may retain references such as `spacetime_evidence_index` and `spacetime_evidence_hash`. The Spacetime hash chain remains owned by Spacetime. A dashboard or API may join the two at read time.

## Verified production provider stack — 5 September 2026

A source-free DSG Spacetime image was deployed to **Azure Container Apps** from private production commit:

```text
commit: 95cf915ed4593720cbfae02d65788726b1c1df87
workflow: 33968246995
result: SUCCESS
image digest: sha256:3cfb71591e5bae45bdbc50a6f51b4af5563a19495aaf267b9627e2efaae212f2
```

The deployment proof executed the following governed production path:

```text
Spacetime
  ↓
GPT-6 Astra proposal
  ↓
Spacetime
  ↓
Claude Sonnet 5 → Remote MCP
  ↓
Spacetime evidence
  ↓
GPT-6 Astra final
```

Verified markers from that production deployment:

- `AZURE_PROVIDER_ASTRA_PROPOSAL=PASS`
- `AZURE_PROVIDER_ANTHROPIC_MCP=PASS`
- `AZURE_PROVIDER_ASTRA_FINAL=PASS`
- `AZURE_PROVIDER_STACK=PASS`
- unauthenticated MCP requests were required to fail closed;
- the governed production Route executed successfully;
- Spacetime evidence remained valid after a new Azure Container Apps revision.

Production endpoints recorded by the deployment workflow:

```text
Health: https://dsg-spacetime-prod.greenglacier-493f3f71.westus3.azurecontainerapps.io/health
MCP:    https://dsg-spacetime-prod.greenglacier-493f3f71.westus3.azurecontainerapps.io/mcp
```

The MCP endpoint requires the configured production authentication boundary. Do not infer anonymous execution capability from the public URL.

### Core Spin production persistence proof

A separate production persistence verification wrote the Core Spin job/history side to Supabase while keeping Spacetime evidence separate:

```text
Core Spin job: 08e4b8be-6b8d-4207-be67-fd8d66873f76
status: COMPLETED
source full-system run: 33966856203
provider sequence: OpenAI → Anthropic → OpenAI
unified read: references_only
spacetime_storage: separate
```

That job contains three `SPACETIME_ROUTE_COMPLETED` correlation events referencing Spacetime evidence indexes `0`, `1`, and `2`; Core Spin does not duplicate the Spacetime decision/request/result/previous hash ledger.

**Claim boundary:** the Core Spin persistence proof and the later Azure provider-stack deployment proof are both verified, but they are different executed runs. Do not represent them as a fresh post-deploy Core Spin→Azure→Core Spin production transaction unless that exact combined run is executed and recorded.

## Why Spacetime

Most teams already have agents, APIs, databases, CI/CD, cloud infrastructure, and automation in production. Replacing that stack just to add governance creates migration cost and operational risk.

Spacetime takes the opposite approach:

- **Keep existing infrastructure.** Add governance around the execution path instead of rebuilding the system.
- **Bind execution to an explicit plan.** Actions are authorized against a concrete plan hash and registered Route.
- **Fail closed.** Missing plans, mismatched hashes, unauthorized Routes, invalid entitlements, unbound agents, and required approvals stop execution.
- **Use offline commercial entitlements.** Signed Ed25519 entitlements can be verified locally at runtime.
- **Keep evidence customer-controlled.** Successful governed executions can produce local tamper-evident evidence records linked by hash.
- **Support swappable agents.** The reasoning provider is not the governance authority; Astra, Claude, GPT, Gemini, customer agents, or other providers can sit behind the same Spacetime boundary when an approved adapter/Route exists.
- **Use provider-native capabilities where appropriate.** MCP or provider-hosted tools can be used as execution transports without giving them authority to bypass Spacetime.

## Runtime model

AI-generated proposals are treated as untrusted input. A proposal must resolve to registered Routes before it can become a bound Spacetime Plan. Execution is checked against the bound plan, plan hash, Route scope, entitlement, agent identity, and configured approval requirement before an adapter is called.

The runtime exposes these MCP capabilities:

```text
spacetime_discover
spacetime_compose
spacetime_execute
spacetime_verify_evidence
```

### MCP transports

The governed MCP runtime can be exposed over stdio or HTTP. Both transports use the same entitlement verification, plan binding, Route authorization, adapter execution, and evidence path.

Local stdio:

```bash
dsg-spacetime serve-mcp \
  --config deployment.json \
  --entitlement entitlement.json \
  --evidence evidence.jsonl
```

Local MCP HTTP:

```bash
dsg-spacetime serve-mcp-http \
  --config deployment.json \
  --entitlement entitlement.json \
  --evidence evidence.jsonl
```

HTTP surface:

```text
POST /mcp     JSON-RPC MCP requests
GET  /health  transport health and MCP protocol version
```

The default HTTP bind is `127.0.0.1:8787`. A non-loopback bind fails closed unless a Bearer API key is supplied through the runtime environment. Browser `Origin` headers are rejected unless explicitly allowlisted.

## Customer-owned trust boundary

DSG Spacetime is intended for customer-hosted or customer-controlled deployment. Runtime configuration, entitlement verification, Route registration, adapter execution, and evidence storage can remain inside the customer's environment.

For Spacetime to act as an enforcement boundary, governed actions must be routed through Spacetime instead of retaining an unrestricted direct execution path around it.

## Publication boundary

This repository is a clean-history, source-visible publication. It intentionally does **not** contain seller signing material, seller trust-root injection tooling, customer or transaction records, private commercial packaging, private release workflows, production secrets, or internal continuity/operator records.

The production provider stack described above is execution evidence from the private production system. It does not mean that private commercial implementation, credentials, or operational records have been published here.

## Source versus commercial binary

The source tree is inspectable and runnable as Python source. Do not treat the source distribution as technically identical to a seller-trust-root-locked compiled commercial binary. Private commercial builds may apply trust-root injection, source-free packaging, signing, and anti-bypass verification outside this repository.

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
