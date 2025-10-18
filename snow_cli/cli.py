"""Command-line interface for ServiceNow CLI"""
import sys
import click
from .config import Config
from .commands import login, elevate, run_script
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


if __name__ == "__main__":
    main()
