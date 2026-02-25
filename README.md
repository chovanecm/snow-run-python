# ServiceNow Python CLI

Run ServiceNow Background Scripts from your terminal — fast, reliable, and cross‑platform. The CLI also handles login, elevation, multi‑instance management, and secure credential storage with persistent sessions.

This tool ships as both a **CLI** and an **MCP (Model Context Protocol) server**, so you can use it directly from the terminal or integrate it with AI assistants like GitHub Copilot and Claude.

## At a Glance

- Run Background Scripts from file or stdin, with parsed output
- Login and persist sessions (cookies saved per instance)
- Elevate to `security_admin` when needed
- Manage multiple instances: add, list, use (set default), remove, info
- Secure credentials via OS keyring (fallback to config file)
- Works on macOS, Linux, and Windows — no GNU/Bash dependencies

## Quickstart

```bash
# Install locally
pip install -e .

# Add your instance and set it as default (interactive for credentials)
snow add --default dev1234.service-now.com

# Login and create a session
snow login

# Run a background script (core feature)
echo "gs.print('Hello');" | snow run
# or from file
snow run example.js

# Elevate if your task requires security_admin
snow elevate
```

## Warning

It would, in the most measured opinion of those entrusted with the uninterrupted prosecution of business-as-usual, be singularly ill-advised to employ this instrument upon any environment denominated as “production”, the consequences of which—while perfectly predictable—would be lamentably time‑consuming to elucidate and even more so to remediate. (Plainly: do not run this on production.)



## Next Generation

This project is the next-generation rewrite of `snow-run`:

- Repository (this project): https://github.com/chovanecm/snow-run-python
- Original Bash version: https://github.com/chovanecm/snow-run
- The original was Bash-based and ran into cross-platform compatibility issues across systems (e.g., GNU vs. BSD tools, Windows shells).
- This Python implementation focuses on consistent behavior across macOS, Linux, and Windows, with easier maintenance and clearer debugging.

## Features

- **Background Scripts (core)**: Run from file or stdin, parsed output, raw HTML saved for troubleshooting
- **Login + elevation**: Authenticate and elevate to `security_admin` when required
- **Persistent sessions**: Cookies stored per instance for reuse
- **Multi-instance management**: add/list/use/remove, with a default instance
- **Secure credentials**: OS keyring when available, config fallback
- **Cross-platform**: macOS, Linux, Windows; no GNU/Bash dependencies
- **Better debugging**: Clear errors; verbose mode planned

## Installation

Choose one of the following:

- Install via pipx (recommended for CLIs)

  ```bash
  pipx install git+https://github.com/chovanecm/snow-run-python@main
  # upgrade later
  pipx upgrade --spec git+https://github.com/chovanecm/snow-run-python@main snow
  ```

- Install via pip (user install)

  ```bash
  python3 -m pip install --user git+https://github.com/chovanecm/snow-run-python@main
  ```

- Pin to a tag or commit

  ```bash
  pipx install "git+https://github.com/chovanecm/snow-run-python@<tag_or_commit>"
  ```

- Try without installing

  ```bash
  pipx run --spec git+https://github.com/chovanecm/snow-run-python@main snow --help
  ```

- Development install from a local clone

  ```bash
  git clone https://github.com/chovanecm/snow-run-python.git
  cd snow-run-python
  pip install -e .
  ```

## Configuration

Use `snow add` to store credentials securely (OS keyring when available) and set a default instance. You can always override with `--instance` for one-off commands. Configuration is stored in `~/.snow-run/config.json` with file permissions set to 600 (owner read/write only). Passwords are stored in the OS keyring when available; otherwise they fall back to the config file.

## Commands

- `snow add [--default] [INSTANCE]` — Add an instance (interactive credentials)
- `snow list` — List configured instances
- `snow use INSTANCE` — Set the default instance
- `snow remove INSTANCE` — Remove an instance
- `snow info` — Show current configuration and paths
- `snow login` — Login and persist session cookies
- `snow elevate` — Elevate to `security_admin`
- `snow run [SCRIPT_FILE|-]` — Run a Background Script (file or stdin)
- `snow record search [options] TABLE_NAME` — Query table records
- `snow record count [-q QUERY] TABLE_NAME` — Count matching records
- `snow r search [options] TABLE_NAME` — Alias for `snow record search`
- `snow r count [-q QUERY] TABLE_NAME` — Alias for `snow record count`
- `snow table fields [options] TABLE_NAME` — List all fields (including inherited) with labels and types
- `snow mcp` — Start the MCP server (stdio) for AI assistant integration

## MCP Server Mode

`snow mcp` starts an [MCP](https://modelcontextprotocol.io/) server over stdio, letting AI assistants (e.g. Claude Desktop) call ServiceNow operations as tools.

**Exposed tools:**

| Tool | Description |
|---|---|
| `snow_run_script` | Execute a JavaScript background script on a ServiceNow instance |
| `snow_login` | Log in and persist the session cookie |
| `snow_elevate` | Elevate to the `security_admin` role |
| `snow_list_instances` | List configured ServiceNow instances |
| `snow_record_count` | Count records matching an optional query. Returns `{"count": N}`. Lightweight — no context concern. |
| `snow_table_fields` | List all fields (including inherited) for a table. Returns `{field, label, type, references}` per field. Use `output_file` for large tables. |
| `snow_record_search` | Query table records with filtering, sorting, projection, limits, and display-value mode. Use `output_file` to save large results to disk and return only metadata. |

All tools accept an optional `instance` argument; omit it to use the default configured instance.

> **Context window tip:** `snow_record_search` and `snow_table_fields` return data inline by default. Always specify `limit` for record searches. For large tables or result sets, pass `output_file` to save to disk — the tool returns only `{"saved_to": "...", "count": N}` instead of the full payload.

> **Security:** Destructive tools (`snow_run_script`, `snow_elevate`, `snow_login`) are annotated so MCP clients will prompt for human confirmation before executing. All MCP calls are logged to `~/.snow-run/audit.log`. See [SECURITY.md](SECURITY.md) for the full MCP threat model and safeguards.

## Table Schema

Use `snow table fields TABLE_NAME` to inspect all columns on a table, including those inherited from parent tables.

```bash
# List all fields (pretty table by default)
snow table fields incident

# JSON output (includes references as a separate key)
snow table fields incident -F json

# Export to CSV for documentation
snow table fields cmdb_ci -F csv -O cmdb_ci_fields.csv

# Export to Excel
snow table fields task -F excel -O task_fields.xlsx
```

### Example output

```
field              label                    type             references
-----------------  -----------------------  ---------------  ----------------
assigned_to        Assignee                 reference        sys_user
caused_by          Caused by Change         reference        change_request
location           Location                 reference        cmn_location
made_sla           Made SLA                 boolean
parent             Parent                   reference        task
sys_updated_on     Updated                  glide_date_time
watch_list         Watch list               glide_list
```

Fields are sorted alphabetically. The `references` column is populated for `reference` and `glide_list` fields that point to another table.

### Options

- `-F, --format [table|tsv|csv|json|xml|excel]` (default: `table`)
- `-O, --output FILE` (write to file; required for excel)

## Record Queries

### Counting records

```bash
# Count all records
snow record count incident

# Count with filter
snow record count -q "active=true" incident
snow r count -q "sys_created_on>=2024-01-01" incident
```

Prints just the integer count — no headers, no formatting.

### Searching records

Use `snow record search` (or alias `snow r search`) to query ServiceNow tables.

```bash
# Basic query — default output is a pretty table
snow record search incident

# Filter + projection + limit
snow record search -q "active=true^priority=1" -f number,short_description,state -l 10 incident

# Sorting (multi)
snow record search -o number -od sys_created_on incident

# sys_id only
snow record search --sys-id incident

# Display mode: values|display|both (default both)
snow record search --display-values both -f caller_id,assignment_group incident
```

### Output formats

Use `-F / --format` to choose the output format:

| Format  | Description                                           |
|---------|-------------------------------------------------------|
| `table` | *(default)* Pretty-printed aligned table              |
| `tsv`   | Tab-separated values                                  |
| `csv`   | Comma-separated values                                |
| `json`  | JSON array (full `value`/`display_value` objects)     |
| `xml`   | ServiceNow XML unload format (`<unload>…</unload>`)   |
| `excel` | Excel `.xlsx` — requires `-O/--output FILE`           |

Use `-O / --output FILE` to write to a file instead of stdout (required for `excel`):

```bash
# CSV to stdout
snow record search -l 20 -f number,state -F csv incident

# JSON to file
snow record search -l 100 -f number,short_description -F json -O incidents.json incident

# Excel export
snow record search -q "active=true" -F excel -O open_incidents.xlsx incident

# ServiceNow XML unload
snow record search -l 10 -F xml incident
```

The XML format follows the ServiceNow XML export convention:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<unload unload_date="2026-02-24 12:00:00">
  <incident action="INSERT_OR_UPDATE">
    <number>INC1234</number>
    <state display_value="Open">1</state>
  </incident>
</unload>
```
Reference fields (where display value differs from raw value) carry a `display_value` attribute.

### All options

- `-q, --query ENCODED_QUERY`
- `-o, --order-by FIELD` (repeatable)
- `-od, --order-by-desc FIELD` (repeatable)
- `-f, --fields FIELDS` (comma-separated)
- `-l, --limit N`
- `-F, --format [table|tsv|csv|json|xml|excel]` (default: `table`)
- `-O, --output FILE` (write to file; required for excel)
- `--no-header`
- `--sys-id` (shortcut for `-f sys_id --no-header`)
- `--display-values [values|display|both]` (default: `both`)

**Claude Desktop setup** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "servicenow": {
      "command": "snow",
      "args": ["mcp"]
    }
  }
}
```

The config file is typically at:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

## Managing Multiple Instances

```bash
# Interactive prompt
snow add

# Specify instance directly
snow add dev1234.service-now.com

# Set as default
snow add --default dev5678.service-now.com

# List configured instances
snow list

# Switch default instance
snow use dev5678.service-now.com

# Remove an instance
snow remove dev1234.service-now.com

# Show info
snow info
```

## Working with Instances

```bash
# Login to default instance
snow login

# Login to specific instance (one-off)
snow --instance dev5678.service-now.com login
# or
snow -i dev5678.service-now.com login

# Run scripts
snow run script.js
echo "gs.print('Hello');" | snow run

# Run on a specific instance
snow -i dev5678.service-now.com run script.js

# Elevate privileges
snow elevate
snow -i dev5678.service-now.com elevate
```

## Troubleshooting & Debugging

- Last raw output (HTML) after running scripts: `~/.snow-run/tmp/{instance}/last_run_output.txt`
- Verbose HTTP logging (`--debug`) is planned.
- On errors, the CLI prints clear messages and relevant HTTP status codes.

## Advanced

Environment variables (legacy override; prefer `snow add`):

```bash
export snow_instance=dev1234.service-now.com
export snow_user=admin
export snow_pwd=your-password

# Example using env vars
snow login
```

## Advantages over Bash version

1. **Platform-independent**: No GNU grep/sed dependencies
2. **Better error handling**: Python exceptions vs shell error codes
3. **Easier to debug**: Can add logging, breakpoints, unit tests
4. **Type hints**: Better IDE support and code documentation
5. **Extensible**: Easy to add new commands and features

## Development

```bash
# Install in development mode
pip install -e .

# Run tests (coming soon)
pytest

# Add logging for debugging
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Migration from Bash

The Python version is designed as a drop-in replacement:

- Same command names: `snow login`, `snow elevate`, `snow run`
- Same environment variables: `snow_instance`, `snow_user`, `snow_pwd`
- Same cookie storage location: `~/.snow-run/tmp/{instance}/cookies.txt`
- Compatible with existing scripts

## TODO

- [ ] Add remaining commands (eval, inspect, table, record, etc.)
- [ ] Add `--debug` flag for verbose HTTP logging
- [ ] Add unit tests
- [ ] Improve output parsing for edge cases
- [ ] Add retry logic for network errors
- [ ] Support for custom SSL certificates
