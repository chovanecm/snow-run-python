"""MCP server mode for ServiceNow CLI"""
import io
import contextlib
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .config import Config
from .commands import login, elevate, run_script

mcp = FastMCP(
    "ServiceNow CLI",
    instructions=(
        "Tools for executing JavaScript background scripts on a ServiceNow instance, "
        "logging in, and elevating privileges. "
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


def serve():
    """Start the MCP server using stdio transport."""
    mcp.run()
