# DSG Spacetime

DSG Spacetime is a governed execution plugin for Claude. It pairs workflow guidance with the DSG remote MCP connector so Claude can discover the capabilities that are currently exposed by the live service, prepare work inside the governed execution boundary, respect approval requirements, and verify evidence before reporting an external effect as successful.

## Use it

Install the plugin, open its **Connectors** tab, and connect **DSG Spacetime** through the authentication flow provided by the remote server.

For read-only work, ask Claude to inspect the current capability surface or verify evidence. For work that can change external state, ask Claude to prepare the action and follow the approval state returned by DSG. A capability or route is available only when the live connector exposes it; this plugin does not treat documentation, examples, or previous sessions as proof of current availability.

Example requests:

- "Show the current DSG capabilities without changing anything."
- "Prepare this browser task and tell me whether approval is required before any external change."
- "Verify the evidence for the last governed action before claiming it succeeded."

## Data sent to DSG

When Claude calls the connector, it sends the arguments required by the selected DSG MCP tool to `https://aws.dsg.pics/mcp`. Depending on the tool, this can include task text, capability or route references, plan or approval references, URLs or resource references, requested action parameters, and evidence-verification inputs.

The plugin does not contain API keys, passwords, bearer tokens, signing material, or other user credentials. Authentication is handled by the remote MCP server through its supported connection flow.

## Governance boundary

Claude should use only capabilities returned by the live service, never invent approval, never bypass a blocked or waiting state, and never treat transport success as proof of the requested external result. Evidence-chain integrity and task success are separate facts and should be reported separately.

## Publication status

This folder is the public Anthropic Directory submission candidate for DSG Spacetime. Repository CI, Claude plugin validation, Developer Portal validation, security review, connector review, and Directory publication are separate gates and must be verified independently.
