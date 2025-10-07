"""Command-line interface for ServiceNow CLI"""
import sys
import click
from .config import Config
from .commands import login, elevate, run_script


@click.group()
@click.option(
    "--instance",
    envvar="snow_instance",
    help="ServiceNow instance (e.g., dev1234.service-now.com)",
)
@click.option("--user", envvar="snow_user", help="ServiceNow username")
@click.option("--password", envvar="snow_pwd", help="ServiceNow password")
@click.pass_context
def main(ctx, instance, user, password):
    """ServiceNow CLI - Platform-independent command-line interface

    Set credentials via environment variables or command-line options:
      export snow_instance=dev1234.service-now.com
      export snow_user=admin
      export snow_pwd=your-password
    """
    # Initialize config and store in context
    config = Config()
    if instance:
        config.instance = instance
    if user:
        config.user = user
    if password:
        config.password = password

    ctx.obj = config


@main.command()
@click.pass_obj
def login_cmd(config):
    """Login to ServiceNow instance and save session"""
    sys.exit(login(config))


@main.command()
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


if __name__ == "__main__":
    main()
