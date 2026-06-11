"""Runtime configuration value object."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """Runtime configuration for a ServiceNow instance."""
    instance: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    cookie_file: Optional[Path] = None
    tmp_dir: Optional[Path] = None

    def ensure_instance_set(self):
        if not self.instance:
            raise ValueError(
                "No instance specified. Use --instance flag or run 'snow use <instance>' to set default."
            )

    def ensure_credentials_set(self):
        self.ensure_instance_set()
        if not self.user or not self.password:
            raise ValueError(
                f"No credentials configured for {self.instance}. Run 'snow add {self.instance}' to configure."
            )
