---
name: servicenow-mcp
description: Use ServiceNow MCP tools to list instances, log in, elevate roles, and run background scripts safely.
---

Use this skill when the user asks to operate on ServiceNow via MCP tools.

## Workflow

1. Start with `snow_list_instances` to discover available instances.
2. If authentication is needed, call `snow_login` (optionally with `instance`).
3. If privileged operations are needed, call `snow_elevate`.
4. Execute JavaScript with `snow_run_script`.

## Tool usage guidance

- Prefer specifying `instance` explicitly when multiple instances exist.
- For script execution, keep scripts focused and return readable output.
- If a call fails, surface stderr and suggest the next corrective action.

## Example prompts

- "List my ServiceNow instances and tell me which one is default."
- "Log in to dev1234.service-now.com and elevate."
- "Run this background script on the default instance: gs.print('hello');"
- "Reverse engineer functionality related to table X (or script Y)"