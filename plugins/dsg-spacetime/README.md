# DSG Spacetime

DSG Spacetime is a portable governed-execution plugin built around the Agent Plugins v1 specification. The public package exposes sanitized workflow skills plus the DSG remote MCP connector so supported agents can discover currently available DSG capabilities, prepare work inside the governed execution boundary, respect approval requirements, and verify evidence before reporting an external effect as successful.

The package intentionally separates the portable core from client-specific compatibility files:

```text
plugin.json                 Agent Plugins v1 portable manifest
mcp.json                    Agent Plugins v1 portable MCP configuration
skills/                     Sanitized portable Agent Skills
.claude-plugin/plugin.json  Claude/Anthropic compatibility manifest
.mcp.json                   Claude/Anthropic MCP compatibility config
```

## Portable Agent Plugins / Google compatibility

The root `plugin.json` and `mcp.json` follow Agent Plugins v1.0.0, the same vendor-neutral package format used by Google's current Google Cloud Developer Plugin. The portable MCP entry uses Streamable HTTP and points only to:

`https://aws.dsg.pics/mcp`

No Google API key, DSG API key, bearer token, password, signing material, or other credential is embedded in the public plugin files.

Google/Antigravity support is treated as a validation target, not as an already-proven compatibility claim. The candidate installation path to test is:

```bash
agy plugin install https://github.com/tdealer01-crypto/DSG-Spacetime-Source/plugins/dsg-spacetime
```

A successful source CI run is not enough to claim Google/Antigravity compatibility. Direct evidence is still required for plugin installation, skill discovery, MCP initialize, authentication, `tools/list`, governed read-only execution, fail-closed behavior for unauthorized privileged actions, and evidence verification.

This repository does not claim that Google lists, endorses, reviews, or publishes DSG in a Google-operated marketplace or directory.

## Claude / Anthropic use

For Claude, install the plugin bundle and connect **DSG Spacetime** through the authentication flow provided by the remote MCP server.

For read-only work, ask Claude to inspect the current capability surface or verify evidence. For work that can change external state, ask Claude to prepare the action and follow the approval state returned by DSG. A capability or route is available only when the live connector exposes it; this plugin does not treat documentation, examples, or previous sessions as proof of current availability.

Example requests:

- "Show the current DSG capabilities without changing anything."
- "Prepare this browser task and tell me whether approval is required before any external change."
- "Verify the evidence for the last governed action before claiming it succeeded."

## Data sent to DSG

When a supported agent calls the connector, it sends the arguments required by the selected DSG MCP tool to `https://aws.dsg.pics/mcp`. Depending on the tool, this can include task text, capability or route references, plan or approval references, URLs or resource references, requested action parameters, and evidence-verification inputs.

The plugin does not contain API keys, passwords, bearer tokens, signing material, or other user credentials. Authentication is handled by the remote MCP server through its supported connection flow.

## Governance boundary

Supported agents should use only capabilities returned by the live service, never invent approval, never bypass a blocked or waiting state, and never treat transport success as proof of the requested external result.

The intended execution boundary is:

`identity → plan → Route → entitlement → approval/policy → adapter → external action → evidence`

The model proposes or requests work; the governed DSG runtime remains the execution authority. Evidence-chain integrity and task success are separate facts and must be reported separately.

## Verification status

This folder is a public cross-ecosystem submission candidate. The following gates are independent and must be verified separately:

- Agent Plugins schema validation
- public exact-head CI
- Google Antigravity install and skill discovery
- Google Antigravity MCP initialize/auth/`tools/list`
- Claude plugin validation
- Claude upload/install
- MCP OAuth/connectivity
- governed read-only execution
- fail-closed negative execution
- evidence-chain verification
- Anthropic Developer Portal validation
- Anthropic connector review
- Directory publication

The presence of files or a green repository CI run must not be reported as proof that any untested client integration, marketplace review, or publication gate has passed.
