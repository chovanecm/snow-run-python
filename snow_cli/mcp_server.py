"""MCP server mode for ServiceNow CLI"""
import io
import contextlib
from typing import Optional, List

from mcp.server.fastmcp import FastMCP

from .config import Config
from .commands import login, elevate, run_script, search_records_json, table_fields_json, count_records_value, _validate_output_file
from .instance_manager import list_instances

mcp = FastMCP(
    "ServiceNow CLI",
    instructions=(
        "Tools for executing JavaScript background scripts on a ServiceNow instance, "
        "logging in, elevating privileges, listing configured instances, and querying tables. "
        "Instances are pre-configured via 'snow add'. "
        "Omit 'instance' to use the default configured instance."
    ),
)


def _run_with_capture(config: Config, fn, *args, **kwargs) -> str:
    """Run a command function and return captured stdout + stderr as a single string."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        exit_code = fn(config, *args, **kwargs)
    output = stdout_buf.getvalue()
    errors = stderr_buf.getvalue()
    parts = []
    if output:
        parts.append(output.rstrip())
    if errors:
        parts.append(f"[stderr]\n{errors.rstrip()}")
    if not parts:
        parts.append("Done." if exit_code == 0 else f"Command failed (exit code {exit_code}).")
    return "\n".join(parts)


def _run_without_config_with_capture(fn, *args, **kwargs) -> str:
    """Run a command function (without config arg) and capture stdout + stderr."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        exit_code = fn(*args, **kwargs)
    output = stdout_buf.getvalue()
    errors = stderr_buf.getvalue()
    parts = []
    if output:
        parts.append(output.rstrip())
    if errors:
        parts.append(f"[stderr]\n{errors.rstrip()}")
    if not parts:
        parts.append("Done." if exit_code == 0 else f"Command failed (exit code {exit_code}).")
    return "\n".join(parts)


@mcp.tool()
def snow_run_script(script: str, instance: Optional[str] = None) -> str:
    """Execute a JavaScript background script on a ServiceNow instance.

    Args:
        script: JavaScript source code to run (e.g. "gs.print('hello');")
        instance: ServiceNow instance hostname (e.g. dev1234.service-now.com).
                  Omit to use the default configured instance.
    """
    config = Config(instance=instance)
    return _run_with_capture(config, run_script, script_content=script)


@mcp.tool()
def snow_login(instance: Optional[str] = None) -> str:
    """Log in to a ServiceNow instance and persist the session cookie.

    Args:
        instance: ServiceNow instance hostname. Omit to use the default instance.
    """
    config = Config(instance=instance)
    return _run_with_capture(config, login)


@mcp.tool()
def snow_elevate(instance: Optional[str] = None) -> str:
    """Elevate privileges to the security_admin role on a ServiceNow instance.

    Args:
        instance: ServiceNow instance hostname. Omit to use the default instance.
    """
    config = Config(instance=instance)
    return _run_with_capture(config, elevate)


@mcp.tool()
def snow_list_instances() -> str:
    """List all configured ServiceNow instances."""
    return _run_without_config_with_capture(list_instances)


@mcp.tool()
def snow_record_search(
    table: str,
    query: Optional[str] = None,
    order_by: Optional[List[str]] = None,
    order_by_desc: Optional[List[str]] = None,
    fields: Optional[str] = None,
    limit: Optional[int] = None,
    display_values: str = "both",
    sys_id: bool = False,
    output_file: Optional[str] = None,
    instance: Optional[str] = None,
) -> str:
    """Search records in a ServiceNow table. Returns JSON array of records.

    Always specify `limit` to avoid large inline responses that consume context.
    Use `output_file` to save results to disk and receive only metadata back —
    ideal for large exports or when the caller does not need the data inline.

    Args:
        table: ServiceNow table name.
        query: Encoded query string (sysparm_query).
        order_by: Field names to sort ascending.
        order_by_desc: Field names to sort descending.
        fields: Comma-separated fields to return.
        limit: Maximum number of records to return. Set this to avoid large responses.
        display_values: One of values, display, both (default both).
        sys_id: Shortcut for fields=sys_id.
        output_file: If set, save JSON results to this file path and return only
                     {"saved_to": "...", "count": N, "fields": [...]} instead of all records.
        instance: ServiceNow instance hostname. Omit to use default instance.
    """
    import json as _json
    config = Config(instance=instance)
    effective_fields = "sys_id" if sys_id else fields
    try:
        records = search_records_json(
            config,
            table=table,
            query=query,
            order_by=order_by,
            order_by_desc=order_by_desc,
            fields=effective_fields,
            limit=limit,
            display_values=display_values,
        )
        if output_file:
            _validate_output_file(output_file)
            with open(output_file, "w", encoding="utf-8") as fh:
                fh.write(_json.dumps(records, ensure_ascii=False, indent=2))
            field_names = list(records[0].keys()) if records else []
            return _json.dumps({"saved_to": output_file, "count": len(records), "fields": field_names})
        return _json.dumps(records, ensure_ascii=False, indent=2)
    except Exception as e:
        return _json.dumps({"error": str(e)})


@mcp.tool()
def snow_table_fields(
    table: str,
    output_file: Optional[str] = None,
    instance: Optional[str] = None,
) -> str:
    """List all fields (including inherited) for a ServiceNow table.

    Returns a JSON array of {field, label, type, references} objects.
    For reference-type fields, 'references' contains the referenced table name.

    For tables with many fields (100+), use output_file to save to disk and
    receive only metadata back — avoiding large inline responses.

    Args:
        table: ServiceNow table name (e.g. incident, cmdb_ci, task).
        output_file: If set, save JSON results to this path and return only
                     {"saved_to": "...", "count": N} instead of all fields.
        instance: ServiceNow instance hostname. Omit to use default instance.
    """
    import json as _json
    config = Config(instance=instance)
    try:
        fields_data = table_fields_json(config, table)
        if output_file:
            _validate_output_file(output_file)
            with open(output_file, "w", encoding="utf-8") as fh:
                fh.write(_json.dumps(fields_data, ensure_ascii=False, indent=2))
            return _json.dumps({"saved_to": output_file, "count": len(fields_data)})
        return _json.dumps(fields_data, ensure_ascii=False, indent=2)
    except Exception as e:
        return _json.dumps({"error": str(e)})


@mcp.tool()
def snow_record_count(
    table: str,
    query: Optional[str] = None,
    instance: Optional[str] = None,
) -> str:
    """Count records in a ServiceNow table using the Aggregate API.

    Returns {"count": N} JSON. Very lightweight — no context window concern.

    Args:
        table: ServiceNow table name (e.g. incident, change_request).
        query: Encoded query string to filter records (sysparm_query).
        instance: ServiceNow instance hostname. Omit to use default instance.
    """
    import json as _json
    config = Config(instance=instance)
    try:
        count = count_records_value(config, table, query=query)
        return _json.dumps({"count": count})
    except Exception as e:
        return _json.dumps({"error": str(e)})


def serve():
    """Start the MCP server using stdio transport."""
    mcp.run()
