---
name: servicenow-mcp
description: Use ServiceNow MCP tools to list instances, log in, elevate roles, query tables, and run background scripts safely.
---

Use this skill when the user asks to operate on ServiceNow via MCP tools.

## Workflow

1. Start with `snow_list_instances` to discover available instances.
2. If authentication is needed, call `snow_login` (optionally with `instance`).
3. If privileged operations are needed, call `snow_elevate`.
4. Query records with `snow_record_search` when table data is needed.
5. Execute JavaScript with `snow_run_script` for operations that cannot be done via Table API.

## Tool usage guidance

- Prefer specifying `instance` explicitly when multiple instances exist.
- For table reads, prefer `snow_record_search` over scripts.
- **Always use `limit`** to control how many records are returned inline — omitting it can return thousands of records and flood the context.
- Use projection (`fields`) to retrieve only the columns you need.
- Choose display mode intentionally: `values`, `display`, or `both` (default).
  - `both` → nested `{"value": ..., "display_value": ...}` objects per field
  - `display` → human-readable labels only (good for presenting to user)
  - `values` → raw values only (good for data processing, export)
- For large exports (> a few hundred records), pass `output_file` to save JSON to disk and receive only metadata back (`{"saved_to": "...", "count": N, "fields": [...]}`). This avoids filling the context window with data.
- For script execution, keep scripts focused and return readable output.
- If a call fails, surface stderr and suggest the next corrective action.

## Example prompts

- "List my ServiceNow instances and tell me which one is default."
- "Log in to dev1234.service-now.com and elevate."
- "Search incident with query active=true, return number and state, limit 20."
- "Export all open incidents to /tmp/open_incidents.json (use output_file)."
- "Run this background script on the default instance: gs.print('hello');"
- "Reverse engineer functionality related to table X (or script Y)"
