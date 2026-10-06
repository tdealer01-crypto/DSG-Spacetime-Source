---
name: full-system-browser
description: Use DSG Spacetime for browser tasks that need live browser capability discovery, governed navigation or actions, approval handling, and evidence verification.
---

# Governed browser work

For browser tasks, first inspect the live DSG capability surface and browser catalog when those tools are available.

Use only browser providers and routes that the live service returns. Do not infer that a browser backend is healthy or available from documentation, a previous session, or cached knowledge.

For browser reads or navigation, follow the permissions and route behavior returned by DSG. For actions that can change external state, keep the work inside the normal DSG planning, approval, execution, and evidence flow.

Never place cookies, passwords, authentication tokens, private keys, or other secret material into prompts, cached browser knowledge, or user-visible evidence.

If the connector exposes advisory browser memory or learned state, treat it as guidance only. Fresh live observation takes precedence, and advisory state never authorizes execution.

Before reporting success, verify the evidence for the requested browser effect. Keep PASS, WAITING_APPROVAL, BLOCKED, REJECTED, FAILED, and VERIFIED outcomes distinct.
