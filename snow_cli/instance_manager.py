"""Instance management commands"""
import sys
import getpass
from .config import Config


def add_instance(instance: str = None, set_default: bool = False):
    """Add a new ServiceNow instance"""
    try:
        # Prompt for instance if not provided
        if not instance:
            instance = input("ServiceNow instance (e.g. dev1234.service-now.com): ").strip()

        if not instance:
            print("Error: Instance is required", file=sys.stderr)
            return 1

        # Prompt for credentials
        user = input(f"Username for {instance}: ").strip()
        if not user:
            print("Error: Username is required", file=sys.stderr)
            return 1

        password = getpass.getpass(f"Password for {user}@{instance}: ")
        if not password:
            print("Error: Password is required", file=sys.stderr)
            return 1

        # Save to config
        config = Config()
        keyring_success = config.save_instance(instance, user, password, set_default)

        print(f"\n✓ Added instance: {instance}")
        print(f"  User: {user}")

        if keyring_success:
            print(f"  Password: Stored in system keyring (secure)")
        else:
            print(f"  Password: Stored in config file (fallback)")
            print(f"  Warning: System keyring not available, using less secure storage")

        if set_default or config.get_default_instance() == instance:
            print(f"  Set as default instance")

        return 0

    except KeyboardInterrupt:
        print("\n\nCancelled.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error adding instance: {e}", file=sys.stderr)
        return 1


def list_instances():
    """List all configured instances"""
    config = Config()
    instances = config.list_instances()
    default = config.get_default_instance()

    if not instances:
        print("No instances configured.")
        print("\nRun 'snow add' to add an instance.")
        return 0

    print("Configured instances:")
    print()
    for instance, creds in instances.items():
        marker = " (default)" if instance == default else ""
        keyring_marker = " [keyring]" if creds.get("keyring") else " [config file]"
        print(f"  {instance}{marker}")
        print(f"    User: {creds['user']}")
        print(f"    Password: Stored in{keyring_marker}")
        print()

    return 0


def use_instance(instance: str):
    """Set default instance"""
    try:
        config = Config()
        config.set_default_instance(instance)
        print(f"✓ Set default instance to: {instance}")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error setting default instance: {e}", file=sys.stderr)
        return 1


def remove_instance(instance: str):
    """Remove an instance"""
    try:
        config = Config()

        # Check if instance exists
        instances = config.list_instances()
        if instance not in instances:
            print(f"Error: Instance {instance} not found", file=sys.stderr)
            return 1

        # Confirm removal
        response = input(f"Remove instance {instance}? [y/N]: ").strip().lower()
        if response not in ("y", "yes"):
            print("Cancelled.")
            return 0

        config.remove_instance(instance)
        print(f"✓ Removed instance: {instance}")
        return 0

    except Exception as e:
        print(f"Error removing instance: {e}", file=sys.stderr)
        return 1


def show_info():
    """Show current configuration"""
    config = Config()

    # Show current/default instance
    if config.instance:
        print(f"Current instance: {config.instance}")
        print(f"  User: {config.user or '(not set)'}")
        print(f"  Password: {'(set)' if config.password else '(not set)'}")
        print(f"  Cookie file: {config.cookie_file}")
    else:
        default = config.get_default_instance()
        if default:
            print(f"Default instance: {default}")
        else:
            print("No instance configured.")

    print()

    # Show all instances
    instances = config.list_instances()
    if instances:
        print(f"Total instances configured: {len(instances)}")
        print("\nRun 'snow list' to see all instances.")
    else:
        print("No instances configured.")
        print("Run 'snow add' to add an instance.")

    return 0
