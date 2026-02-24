"""MCP server mode for ServiceNow CLI"""
import io
import contextlib
from typing import Optional, List

from mcp.server.fastmcp import FastMCP

from .config import Config
from .commands import login, elevate, run_script, search_records_json
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
    instance: Optional[str] = None,
) -> str:
    """Search records in a ServiceNow table. Returns JSON array of records.

    Args:
        table: ServiceNow table name.
        query: Encoded query string (sysparm_query).
        order_by: Field names to sort ascending.
        order_by_desc: Field names to sort descending.
        fields: Comma-separated fields to return.
        limit: Maximum number of records to return.
        display_values: One of values, display, both.
        sys_id: Shortcut for fields=sys_id.
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
        return _json.dumps(records, ensure_ascii=False, indent=2)
    except Exception as e:
        return _json.dumps({"error": str(e)})


def serve():
    """Start the MCP server using stdio transport."""
    mcp.run()
