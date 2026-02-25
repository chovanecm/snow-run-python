"""Configuration management for ServiceNow CLI"""
import os
import json
from pathlib import Path
from typing import Optional, Dict
import keyring


class Config:
    """Manages ServiceNow CLI configuration and state"""

    def __init__(self, instance: Optional[str] = None):
        self.snow_dir = Path.home() / ".snow-run"
        self.config_file = self.snow_dir / "config.json"

        # Try to load from environment first, then config file
        self.instance: Optional[str] = instance or os.environ.get("snow_instance")
        self.user: Optional[str] = os.environ.get("snow_user")
        self.password: Optional[str] = os.environ.get("snow_pwd")

        # If not in env, try to load from config file
        if not self.instance or not self.user or not self.password:
            self._load_from_file()

    def _load_from_file(self):
        """Load configuration from file"""
        if not self.config_file.exists():
            return

        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)

            # Get default instance if not specified
            if not self.instance:
                self.instance = config.get("default_instance")

            # Load credentials for the instance
            if self.instance and "instances" in config:
                instance_config = config["instances"].get(self.instance, {})
                if not self.user:
                    self.user = instance_config.get("user")
                if not self.password:
                    # Try keyring first, fall back to config file
                    self.password = self._get_password_from_keyring(self.instance, self.user)
                    if not self.password:
                        # Legacy: check config file for password
                        self.password = instance_config.get("password")
        except (json.JSONDecodeError, KeyError) as e:
            # Ignore corrupted config file
            pass

    def _get_password_from_keyring(self, instance: str, user: str) -> Optional[str]:
        """Get password from system keyring"""
        if not user:
            return None
        try:
            return keyring.get_password(f"snow-cli:{instance}", user)
        except Exception:
            # Keyring not available or other error
            return None

    def _set_password_in_keyring(self, instance: str, user: str, password: str):
        """Store password in system keyring"""
        try:
            keyring.set_password(f"snow-cli:{instance}", user, password)
            return True
        except Exception as e:
            # Keyring not available
            return False

    def _delete_password_from_keyring(self, instance: str, user: str):
        """Delete password from system keyring"""
        try:
            keyring.delete_password(f"snow-cli:{instance}", user)
        except Exception:
            pass

    def save_instance(self, instance: str, user: str, password: str, set_default: bool = False):
        """Save instance configuration to file"""
        self.snow_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Load existing config
        config = {}
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
            except json.JSONDecodeError:
                config = {}

        # Update config
        if "instances" not in config:
            config["instances"] = {}

        # Try to save password to keyring
        keyring_success = self._set_password_in_keyring(instance, user, password)

        # Store instance config (username only if keyring worked)
        config["instances"][instance] = {
            "user": user,
            "keyring": keyring_success
        }

        # If keyring failed, fall back to storing password in config file
        if not keyring_success:
            config["instances"][instance]["password"] = password

        if set_default or "default_instance" not in config:
            config["default_instance"] = instance

        # Save config with restricted permissions
        fd = os.open(str(self.config_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(config, indent=2))

        return keyring_success

    def list_instances(self) -> Dict[str, Dict[str, str]]:
        """List all configured instances"""
        if not self.config_file.exists():
            return {}

        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            return config.get("instances", {})
        except json.JSONDecodeError:
            return {}

    def get_default_instance(self) -> Optional[str]:
        """Get default instance"""
        if not self.config_file.exists():
            return None

        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            return config.get("default_instance")
        except json.JSONDecodeError:
            return None

    def set_default_instance(self, instance: str):
        """Set default instance"""
        if not self.config_file.exists():
            raise ValueError(f"Instance {instance} not configured. Run 'snow add' first.")

        with open(self.config_file, 'r') as f:
            config = json.load(f)

        if instance not in config.get("instances", {}):
            raise ValueError(f"Instance {instance} not configured. Run 'snow add' first.")

        config["default_instance"] = instance
        fd = os.open(str(self.config_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(config, indent=2))

    def remove_instance(self, instance: str):
        """Remove instance configuration"""
        if not self.config_file.exists():
            return

        with open(self.config_file, 'r') as f:
            config = json.load(f)

        if "instances" in config and instance in config["instances"]:
            # Remove password from keyring if it exists
            instance_config = config["instances"][instance]
            user = instance_config.get("user")
            if user:
                self._delete_password_from_keyring(instance, user)

            del config["instances"][instance]

            # If this was the default, clear it
            if config.get("default_instance") == instance:
                # Set new default to first available instance
                if config["instances"]:
                    config["default_instance"] = next(iter(config["instances"]))
                else:
                    config["default_instance"] = None

            fd = os.open(str(self.config_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(config, indent=2))

    @property
    def tmp_dir(self) -> Path:
        """Get temp directory for current instance"""
        if not self.instance:
            raise ValueError("snow_instance not set")
        path = self.snow_dir / "tmp" / self.instance
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    @property
    def cookie_file(self) -> Path:
        """Get cookie file path"""
        return self.tmp_dir / "cookies.txt"

    def ensure_instance_set(self):
        """Ensure instance is configured"""
        if not self.instance:
            raise ValueError(
                "No instance specified. Use --instance flag or run 'snow use <instance>' to set default."
            )

    def ensure_credentials_set(self):
        """Ensure credentials are configured"""
        self.ensure_instance_set()
        if not self.user or not self.password:
            raise ValueError(
                f"No credentials configured for {self.instance}. Run 'snow add {self.instance}' to configure."
            )
