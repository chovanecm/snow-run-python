"""Command-line interface for ServiceNow CLI"""
import sys
import click
from .config import Config
from .commands import login, elevate, run_script, search_records
from .instance_manager import add_instance, list_instances, use_instance, remove_instance, show_info

@click.group()
@click.option(
    "-i", "--instance",
    envvar="snow_instance",
    help="ServiceNow instance (overrides default)",
)
@click.pass_context
def main(ctx, instance):
    """ServiceNow CLI - Platform-independent command-line interface

    Manage multiple ServiceNow instances:
      snow add                    # Add a new instance
      snow list                   # List all instances
      snow use <instance>         # Set default instance
      snow login                  # Login to default instance
      snow --instance dev2 login  # Login to specific instance
    """
    # Initialize config with specified instance
    config = Config(instance=instance)
    ctx.obj = config


@main.command(name="login")
@click.pass_obj
def login_cmd(config):
    """Login to ServiceNow instance and save session"""
    sys.exit(login(config))


@main.command(name="elevate")
@click.pass_obj
def elevate_cmd(config):
    """Elevate user privileges (security_admin role)"""
    sys.exit(elevate(config))


@main.command()
@click.argument("script_file", required=False)
@click.pass_obj
def run(config, script_file):
    """Run a background script on ServiceNow

    SCRIPT_FILE: Path to JavaScript file to execute (or '-' for stdin)

    Examples:
      snow run example.js
      echo "gs.print('Hello');" | snow run
      snow run < script.js
    """
    sys.exit(run_script(config, script_file))


@main.command()
@click.argument("instance", required=False)
@click.option("--default", is_flag=True, help="Set as default instance")
def add(instance, default):
    """Add a new ServiceNow instance

    INSTANCE: ServiceNow instance (e.g. dev1234.service-now.com)

    Examples:
      snow add dev1234.service-now.com
      snow add --default dev1234.service-now.com
      snow add  # Interactive prompt
    """
    sys.exit(add_instance(instance, default))


@main.command("list")
def list_cmd():
    """List all configured instances"""
    sys.exit(list_instances())


@main.group()
def record():
    """Record operations."""


@main.group(name="r")
def r_alias():
    """Alias for record."""


def _record_search_impl(config, table, query, order_by, order_by_desc, fields, limit, no_header, sys_id, display_values, fmt, output_file):
    sys.exit(
        search_records(
            config=config,
            table=table,
            query=query,
            order_by=order_by,
            order_by_desc=order_by_desc,
            fields=fields,
            limit=limit,
            no_header=no_header,
            sys_id=sys_id,
            display_values=display_values,
            fmt=fmt,
            output_file=output_file,
        )
    )


_FORMAT_OPTION = [
    click.option(
        "-F", "--format", "fmt",
        type=click.Choice(["table", "tsv", "csv", "json", "xml", "excel"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format",
    ),
    click.option("-O", "--output", "output_file", default=None, help="Write output to FILE (required for excel)"),
]


def _add_format_options(func):
    for option in reversed(_FORMAT_OPTION):
        func = option(func)
    return func


@record.command(name="search")
@click.option("-q", "--query", "query", help="Encoded query (sysparm_query)")
@click.option("-o", "--order-by", "order_by", multiple=True, help="Order by field (can be used multiple times)")
@click.option("-od", "--order-by-desc", "order_by_desc", multiple=True, help="Order by field descending (can be used multiple times)")
@click.option("-f", "--fields", help="Comma-separated list of fields to return")
@click.option("-l", "--limit", type=int, help="Maximum number of records to return")
@click.option("--no-header", is_flag=True, help="Omit column headers")
@click.option("--sys-id", "sys_id", is_flag=True, help="Shortcut for -f sys_id --no-header")
@click.option(
    "--display-values",
    type=click.Choice(["values", "display", "both"], case_sensitive=False),
    default="both",
    show_default=True,
    help="Return field values, display values, or both",
)
@_add_format_options
@click.argument("table_name")
@click.pass_obj
def record_search(config, query, order_by, order_by_desc, fields, limit, no_header, sys_id, display_values, fmt, output_file, table_name):
    """Perform a query on a table."""
    _record_search_impl(
        config,
        table_name,
        query,
        list(order_by),
        list(order_by_desc),
        fields,
        limit,
        no_header,
        sys_id,
        display_values.lower(),
        fmt.lower(),
        output_file,
    )


@r_alias.command(name="search")
@click.option("-q", "--query", "query", help="Encoded query (sysparm_query)")
@click.option("-o", "--order-by", "order_by", multiple=True, help="Order by field (can be used multiple times)")
@click.option("-od", "--order-by-desc", "order_by_desc", multiple=True, help="Order by field descending (can be used multiple times)")
@click.option("-f", "--fields", help="Comma-separated list of fields to return")
@click.option("-l", "--limit", type=int, help="Maximum number of records to return")
@click.option("--no-header", is_flag=True, help="Omit column headers")
@click.option("--sys-id", "sys_id", is_flag=True, help="Shortcut for -f sys_id --no-header")
@click.option(
    "--display-values",
    type=click.Choice(["values", "display", "both"], case_sensitive=False),
    default="both",
    show_default=True,
    help="Return field values, display values, or both",
)
@_add_format_options
@click.argument("table_name")
@click.pass_obj
def r_search(config, query, order_by, order_by_desc, fields, limit, no_header, sys_id, display_values, fmt, output_file, table_name):
    """Perform a query on a table."""
    _record_search_impl(
        config,
        table_name,
        query,
        list(order_by),
        list(order_by_desc),
        fields,
        limit,
        no_header,
        sys_id,
        display_values.lower(),
        fmt.lower(),
        output_file,
    )


@main.command()
@click.argument("instance")
def use(instance):
    """Set default instance

    Examples:
      snow use dev1234.service-now.com
    """
    sys.exit(use_instance(instance))


@main.command()
@click.argument("instance")
def remove(instance):
    """Remove an instance

    Examples:
      snow remove dev1234.service-now.com
    """
    sys.exit(remove_instance(instance))


@main.command()
def info():
    """Show current configuration and instances"""
    sys.exit(show_info())


@main.command()
def mcp():
    """Start the MCP server (stdio transport) for AI assistant integration

    Exposes snow_run_script, snow_login, snow_elevate, snow_list_instances, and snow_record_search as MCP tools.

    Example Claude Desktop config (~/.config/claude/claude_desktop_config.json):

    \b
    {
      "mcpServers": {
        "servicenow": {
          "command": "snow",
          "args": ["mcp"]
        }
      }
    }
    """
    from .mcp_server import serve
    serve()


if __name__ == "__main__":
    main()
