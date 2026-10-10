---
name: governed-execution
description: Use DSG Spacetime when a task needs live capability discovery, plan-aligned governed execution, approval-aware actions, or evidence verification.
---

# Governed execution

Use DSG Spacetime as the execution boundary instead of calling an external system directly when the requested work is meant to be governed by DSG.

1. Discover the capabilities required for the user's goal from the live DSG connector.
2. Use only capabilities and routes returned by the live service. Do not invent providers, permissions, credentials, approvals, or route availability.
3. Prepare or compose the requested work with the DSG planning tools exposed by the connector.
4. If DSG reports that approval is required, treat the request as waiting for approval rather than as completed. Never invent, infer, or bypass approval.
5. Execute only when the connector reports that the request is authorized for execution.
6. After material execution, verify the returned evidence before claiming that the requested external effect succeeded.

Keep these distinctions explicit:

- configuration or catalog presence is not provider-health proof;
- successful tool transport is not proof of the requested external result;
- evidence-chain validity is not the same thing as task success;
- a blocked, rejected, failed, or waiting request must not be reported as completed.

If the live service does not expose a capability needed for the task, report the missing capability instead of substituting an ungoverned path.
