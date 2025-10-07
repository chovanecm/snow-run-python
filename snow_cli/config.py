"""Configuration management for ServiceNow CLI"""
import os
from pathlib import Path
from typing import Optional


class Config:
    """Manages ServiceNow CLI configuration and state"""

    def __init__(self):
        self.snow_dir = Path.home() / ".snow-run"
        self.instance: Optional[str] = os.environ.get("snow_instance")
        self.user: Optional[str] = os.environ.get("snow_user")
        self.password: Optional[str] = os.environ.get("snow_pwd")

    @property
    def tmp_dir(self) -> Path:
        """Get temp directory for current instance"""
        if not self.instance:
            raise ValueError("snow_instance not set")
        path = self.snow_dir / "tmp" / self.instance
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cookie_file(self) -> Path:
        """Get cookie file path"""
        return self.tmp_dir / "cookies.txt"

    def ensure_instance_set(self):
        """Ensure instance is configured"""
        if not self.instance:
            raise ValueError(
                "snow_instance not set. "
                "Set it via environment variable or snow_instance=your-instance.service-now.com"
            )

    def ensure_credentials_set(self):
        """Ensure credentials are configured"""
        self.ensure_instance_set()
        if not self.user or not self.password:
            raise ValueError(
                "Credentials not set. "
                "Set snow_user and snow_pwd environment variables"
            )
