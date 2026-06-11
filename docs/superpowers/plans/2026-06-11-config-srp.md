# Config SRP Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract all I/O, keyring, and path logic from `Config` into a new `InstanceRepository`, leaving `Config` as a lean dataclass.

**Architecture:** Four sequential tasks, each ending with a green test suite and a commit. Tasks 1–3 add new functionality without breaking existing behaviour; Task 4 is test cleanup only.

**Tech Stack:** Python 3, dataclasses, keyring, unittest/pytest

---

## File map

| File | Task | Change |
|---|---|---|
| `snow_cli/instance_repository.py` | 1, 2 | **New** — CRUD, path helpers, `_load_json`/`_save_json`, keyring, `load_config` |
| `snow_cli/config.py` | 2 | **Rewrite** — lean `@dataclass`, ~25 lines |
| `snow_cli/cli.py` | 2 | Replace `Config(instance=instance)` with `InstanceRepository().load_config(instance=instance)` |
| `snow_cli/commands.py` | 2 | Add one `mkdir` in `_run_script_once` |
| `snow_cli/instance_manager.py` | 3 | Import swap + method renames |
| `tests/test_instance_repository.py` | 1, 2 | **New** — tests for `InstanceRepository` |
| `tests/test_commands.py` | 2, 4 | Update `SilentExceptionTests`; replace `DummyConfig` |

---

## Task 1: Create `InstanceRepository` (CRUD, paths, I/O)

**Files:**
- Create: `tests/test_instance_repository.py`
- Create: `snow_cli/instance_repository.py`

- [ ] **Step 1: Create the test file**

```python
# tests/test_instance_repository.py
import io
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

keyring_stub = types.SimpleNamespace(
    get_password=lambda *a, **kw: None,
    set_password=lambda *a, **kw: None,
    delete_password=lambda *a, **kw: None,
)
sys.modules.setdefault("keyring", keyring_stub)

from snow_cli.instance_repository import InstanceRepository


class LoadJsonTests(unittest.TestCase):
    def test_returns_empty_dict_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = InstanceRepository(snow_dir=Path(tmp) / ".snow-run")
            self.assertEqual(repo._load_json(), {})

    def test_returns_data_for_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            snow_dir = Path(tmp) / ".snow-run"
            snow_dir.mkdir()
            (snow_dir / "config.json").write_text(
                '{"default_instance": "dev.service-now.com"}'
            )
            repo = InstanceRepository(snow_dir=snow_dir)
            self.assertEqual(repo._load_json()["default_instance"], "dev.service-now.com")

    def test_returns_empty_dict_and_warns_for_corrupted_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            snow_dir = Path(tmp) / ".snow-run"
            snow_dir.mkdir()
            (snow_dir / "config.json").write_text("{ not valid json }")
            repo = InstanceRepository(snow_dir=snow_dir)
            buf = io.StringIO()
            with redirect_stderr(buf):
                result = repo._load_json()
            self.assertEqual(result, {})
            self.assertIn("Warning", buf.getvalue())


class PathHelperTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = InstanceRepository(snow_dir=Path(self._tmp.name) / ".snow-run")

    def tearDown(self):
        self._tmp.cleanup()

    def test_cookie_file_for_returns_expected_path(self):
        expected = self.repo.snow_dir / "tmp" / "dev.service-now.com" / "cookies.txt"
        self.assertEqual(self.repo.cookie_file_for("dev.service-now.com"), expected)

    def test_tmp_dir_for_returns_expected_path(self):
        expected = self.repo.snow_dir / "tmp" / "dev.service-now.com"
        self.assertEqual(self.repo.tmp_dir_for("dev.service-now.com"), expected)


class InstanceRepositoryCrudTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = InstanceRepository(snow_dir=Path(self._tmp.name) / ".snow-run")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_config(self, data: dict):
        self.repo.snow_dir.mkdir(parents=True, exist_ok=True)
        (self.repo.snow_dir / "config.json").write_text(json.dumps(data))

    def test_save_persists_instance_and_user_to_file(self):
        self.repo.save("dev.service-now.com", "admin", "pass123")
        data = self.repo._load_json()
        self.assertIn("dev.service-now.com", data["instances"])
        self.assertEqual(data["instances"]["dev.service-now.com"]["user"], "admin")

    def test_save_sets_default_when_no_existing_default(self):
        self.repo.save("dev.service-now.com", "admin", "pass123")
        self.assertEqual(self.repo.get_default(), "dev.service-now.com")

    def test_save_does_not_overwrite_existing_default(self):
        self.repo.save("dev1.service-now.com", "admin", "pass1")
        self.repo.save("dev2.service-now.com", "admin", "pass2")
        self.assertEqual(self.repo.get_default(), "dev1.service-now.com")

    def test_save_with_set_default_true_changes_default(self):
        self.repo.save("dev1.service-now.com", "admin", "pass1")
        self.repo.save("dev2.service-now.com", "admin", "pass2", set_default=True)
        self.assertEqual(self.repo.get_default(), "dev2.service-now.com")

    def test_save_stores_password_in_file_when_keyring_unavailable(self):
        failing_keyring = types.SimpleNamespace(
            get_password=lambda *a, **kw: None,
            set_password=lambda *a, **kw: (_ for _ in ()).throw(Exception("no keyring")),
            delete_password=lambda *a, **kw: None,
        )
        with patch.dict(sys.modules, {"keyring": failing_keyring}):
            import importlib
            import snow_cli.instance_repository as ir_mod
            importlib.reload(ir_mod)
            repo = ir_mod.InstanceRepository(snow_dir=Path(self._tmp.name) / ".snow-run-kr")
            repo.save("dev.service-now.com", "admin", "pass123")
            data = repo._load_json()
        importlib.reload(ir_mod)  # restore module state
        self.assertEqual(data["instances"]["dev.service-now.com"].get("password"), "pass123")
        self.assertFalse(data["instances"]["dev.service-now.com"]["keyring"])

    def test_list_all_returns_all_instances(self):
        self.repo.save("dev1.service-now.com", "admin", "pass1")
        self.repo.save("dev2.service-now.com", "admin", "pass2")
        instances = self.repo.list_all()
        self.assertIn("dev1.service-now.com", instances)
        self.assertIn("dev2.service-now.com", instances)

    def test_list_all_returns_empty_dict_when_no_config(self):
        self.assertEqual(self.repo.list_all(), {})

    def test_get_default_returns_none_when_no_config(self):
        self.assertIsNone(self.repo.get_default())

    def test_set_default_changes_default(self):
        self.repo.save("dev1.service-now.com", "admin", "pass1")
        self.repo.save("dev2.service-now.com", "admin", "pass2")
        self.repo.set_default("dev2.service-now.com")
        self.assertEqual(self.repo.get_default(), "dev2.service-now.com")

    def test_set_default_raises_for_unknown_instance(self):
        with self.assertRaises(ValueError):
            self.repo.set_default("unknown.service-now.com")

    def test_remove_deletes_instance(self):
        self.repo.save("dev.service-now.com", "admin", "pass")
        self.repo.remove("dev.service-now.com")
        self.assertNotIn("dev.service-now.com", self.repo.list_all())

    def test_remove_rotates_default_to_next_instance(self):
        self.repo.save("dev1.service-now.com", "admin", "pass1")
        self.repo.save("dev2.service-now.com", "admin", "pass2")
        self.repo.remove("dev1.service-now.com")
        self.assertEqual(self.repo.get_default(), "dev2.service-now.com")

    def test_remove_sets_default_to_none_when_last_instance_removed(self):
        self.repo.save("dev.service-now.com", "admin", "pass")
        self.repo.remove("dev.service-now.com")
        self.assertIsNone(self.repo.get_default())

    def test_remove_is_noop_for_nonexistent_instance(self):
        self.repo.save("dev.service-now.com", "admin", "pass")
        self.repo.remove("other.service-now.com")  # must not raise
        self.assertIn("dev.service-now.com", self.repo.list_all())
```

- [ ] **Step 2: Run tests to confirm they fail (module not yet created)**

```bash
python -m pytest tests/test_instance_repository.py -v
```

Expected: `ModuleNotFoundError: No module named 'snow_cli.instance_repository'`

- [ ] **Step 3: Create `snow_cli/instance_repository.py`**

```python
"""Instance storage: file persistence, keyring, and path computation."""
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

import keyring


class InstanceRepository:
    """Owns all file-system and keyring I/O for instance storage."""

    def __init__(self, snow_dir: Optional[Path] = None):
        self.snow_dir = snow_dir or Path.home() / ".snow-run"
        self.config_file = self.snow_dir / "config.json"

    # ---------- path helpers ----------

    def cookie_file_for(self, instance: str) -> Path:
        return self.snow_dir / "tmp" / instance / "cookies.txt"

    def tmp_dir_for(self, instance: str) -> Path:
        return self.snow_dir / "tmp" / instance

    # ---------- CRUD ----------

    def save(self, instance: str, user: str, password: str, set_default: bool = False) -> bool:
        """Persist instance credentials. Returns True if password was stored in keyring."""
        data = self._load_json()
        if "instances" not in data:
            data["instances"] = {}
        keyring_success = self._set_password_in_keyring(instance, user, password)
        data["instances"][instance] = {"user": user, "keyring": keyring_success}
        if not keyring_success:
            data["instances"][instance]["password"] = password
        if set_default or "default_instance" not in data:
            data["default_instance"] = instance
        self._save_json(data)
        return keyring_success

    def remove(self, instance: str):
        data = self._load_json()
        if instance not in data.get("instances", {}):
            return
        user = data["instances"][instance].get("user")
        if user:
            self._delete_password_from_keyring(instance, user)
        del data["instances"][instance]
        if data.get("default_instance") == instance:
            remaining = list(data["instances"])
            data["default_instance"] = remaining[0] if remaining else None
        self._save_json(data)

    def list_all(self) -> Dict[str, Dict]:
        return self._load_json().get("instances", {})

    def get_default(self) -> Optional[str]:
        return self._load_json().get("default_instance")

    def set_default(self, instance: str):
        data = self._load_json()
        if instance not in data.get("instances", {}):
            raise ValueError(f"Instance {instance} not configured. Run 'snow add' first.")
        data["default_instance"] = instance
        self._save_json(data)

    # ---------- private I/O ----------

    def _load_json(self) -> dict:
        """Return config dict; {} if file is absent; {} + stderr warning if corrupted."""
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Warning: config file is corrupted and will be ignored ({e})", file=sys.stderr)
            return {}

    def _save_json(self, data: dict):
        self.snow_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(self.config_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2))

    # ---------- keyring ----------

    def _get_password_from_keyring(self, instance: str, user: str) -> Optional[str]:
        if not user:
            return None
        try:
            return keyring.get_password(f"snow-cli:{instance}", user)
        except Exception:
            return None

    def _set_password_in_keyring(self, instance: str, user: str, password: str) -> bool:
        try:
            keyring.set_password(f"snow-cli:{instance}", user, password)
            return True
        except Exception:
            return False

    def _delete_password_from_keyring(self, instance: str, user: str):
        try:
            keyring.delete_password(f"snow-cli:{instance}", user)
        except Exception:
            pass
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_instance_repository.py -v
```

Expected: all tests **PASS**.

- [ ] **Step 5: Run the full test suite to confirm nothing broken**

```bash
python -m pytest tests/ -v
```

Expected: all tests **PASS**.

- [ ] **Step 6: Commit**

```bash
git add snow_cli/instance_repository.py tests/test_instance_repository.py
git commit -m "refactor: add InstanceRepository with CRUD, path helpers, and I/O"
```

---

## Task 2: Add `load_config` + rewrite `Config` + update `cli.py` + update `commands.py`

These four changes are a single atomic unit: `load_config` returns the new `Config`, `cli.py` calls `load_config`, and `commands.py` gains an explicit `mkdir` to replace the old side-effectful `tmp_dir` property.

**Files:**
- Modify: `tests/test_instance_repository.py` (add `LoadConfigTests`)
- Modify: `tests/test_commands.py` (update `SilentExceptionTests`)
- Modify: `snow_cli/instance_repository.py` (add `load_config`)
- Modify: `snow_cli/config.py` (full rewrite)
- Modify: `snow_cli/cli.py` (1-line change + import swap)
- Modify: `snow_cli/commands.py` (1 `mkdir` addition)

- [ ] **Step 1: Add `LoadConfigTests` to `tests/test_instance_repository.py`**

Append this class to `tests/test_instance_repository.py`:

```python
class LoadConfigTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = InstanceRepository(snow_dir=Path(self._tmp.name) / ".snow-run")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_config(self, data: dict):
        self.repo.snow_dir.mkdir(parents=True, exist_ok=True)
        (self.repo.snow_dir / "config.json").write_text(json.dumps(data))

    def test_returns_none_fields_when_nothing_configured(self):
        config = self.repo.load_config()
        self.assertIsNone(config.instance)
        self.assertIsNone(config.user)
        self.assertIsNone(config.password)
        self.assertIsNone(config.cookie_file)
        self.assertIsNone(config.tmp_dir)

    def test_instance_arg_takes_priority_over_env(self):
        with patch.dict(os.environ, {"snow_instance": "env.service-now.com"}):
            config = self.repo.load_config(instance="arg.service-now.com")
        self.assertEqual(config.instance, "arg.service-now.com")

    def test_resolves_instance_from_snow_instance_env_var(self):
        with patch.dict(os.environ, {"snow_instance": "env.service-now.com"},
                        clear=False):
            config = self.repo.load_config()
        self.assertEqual(config.instance, "env.service-now.com")

    def test_resolves_instance_from_file_default_instance(self):
        self._write_config({
            "default_instance": "file.service-now.com",
            "instances": {"file.service-now.com": {"user": "admin", "keyring": False, "password": "p"}}
        })
        config = self.repo.load_config()
        self.assertEqual(config.instance, "file.service-now.com")

    def test_computes_cookie_file_and_tmp_dir_when_instance_known(self):
        self._write_config({
            "default_instance": "dev.service-now.com",
            "instances": {"dev.service-now.com": {"user": "admin", "keyring": False, "password": "p"}}
        })
        config = self.repo.load_config()
        self.assertEqual(config.cookie_file, self.repo.cookie_file_for("dev.service-now.com"))
        self.assertEqual(config.tmp_dir, self.repo.tmp_dir_for("dev.service-now.com"))

    def test_cookie_file_and_tmp_dir_are_none_when_no_instance(self):
        config = self.repo.load_config()
        self.assertIsNone(config.cookie_file)
        self.assertIsNone(config.tmp_dir)

    def test_credentials_from_env_override_file(self):
        self._write_config({
            "default_instance": "dev.service-now.com",
            "instances": {"dev.service-now.com": {"user": "file_user", "keyring": False, "password": "file_pass"}}
        })
        with patch.dict(os.environ, {"snow_user": "env_user", "snow_pwd": "env_pass"}, clear=False):
            config = self.repo.load_config()
        self.assertEqual(config.user, "env_user")
        self.assertEqual(config.password, "env_pass")

    def test_resolves_user_and_password_from_file(self):
        self._write_config({
            "default_instance": "dev.service-now.com",
            "instances": {
                "dev.service-now.com": {"user": "admin", "keyring": False, "password": "s3cr3t"}
            }
        })
        config = self.repo.load_config()
        self.assertEqual(config.user, "admin")
        self.assertEqual(config.password, "s3cr3t")
```

- [ ] **Step 2: Update `SilentExceptionTests` in `tests/test_commands.py`**

Replace the existing `test_corrupted_config_file_prints_warning_to_stderr` test body:

```python
# BEFORE (in SilentExceptionTests):
def test_corrupted_config_file_prints_warning_to_stderr(self):
    from snow_cli.config import Config
    with tempfile.TemporaryDirectory() as tmp_dir:
        snow_dir = Path(tmp_dir) / ".snow-run"
        snow_dir.mkdir()
        config_file = snow_dir / "config.json"
        config_file.write_text("{ not valid json }")

        config = Config.__new__(Config)
        config.snow_dir = snow_dir
        config.config_file = config_file
        config.instance = None
        config.user = None
        config.password = None

        buf = io.StringIO()
        with redirect_stderr(buf):
            config._load_from_file()

        self.assertIn("Warning", buf.getvalue())
```

Replace with:

```python
def test_corrupted_config_file_prints_warning_to_stderr(self):
    from snow_cli.instance_repository import InstanceRepository
    with tempfile.TemporaryDirectory() as tmp_dir:
        snow_dir = Path(tmp_dir) / ".snow-run"
        snow_dir.mkdir()
        (snow_dir / "config.json").write_text("{ not valid json }")

        repo = InstanceRepository(snow_dir=snow_dir)
        buf = io.StringIO()
        with redirect_stderr(buf):
            repo.load_config()

        self.assertIn("Warning", buf.getvalue())
```

- [ ] **Step 3: Run the new tests to confirm they fail**

```bash
python -m pytest tests/test_instance_repository.py::LoadConfigTests tests/test_commands.py::SilentExceptionTests::test_corrupted_config_file_prints_warning_to_stderr -v
```

Expected: `LoadConfigTests` fails with `AttributeError: 'InstanceRepository' object has no attribute 'load_config'`; `SilentExceptionTests` test fails.

- [ ] **Step 4: Add `load_config` to `snow_cli/instance_repository.py`**

Add this method to the `InstanceRepository` class, after `set_default` and before `_load_json`:

```python
def load_config(self, instance: Optional[str] = None) -> "Config":
    """Resolve credentials from env vars and config file; return a populated Config."""
    from .config import Config

    instance = instance or os.environ.get("snow_instance")
    user = os.environ.get("snow_user")
    password = os.environ.get("snow_pwd")

    if not instance or not user or not password:
        data = self._load_json()
        if not instance:
            instance = data.get("default_instance")
        if instance and "instances" in data:
            inst_cfg = data["instances"].get(instance, {})
            if not user:
                user = inst_cfg.get("user")
            if not password:
                password = self._get_password_from_keyring(instance, user)
                if not password:
                    password = inst_cfg.get("password")

    cookie_file = self.cookie_file_for(instance) if instance else None
    tmp_dir = self.tmp_dir_for(instance) if instance else None
    return Config(
        instance=instance,
        user=user,
        password=password,
        cookie_file=cookie_file,
        tmp_dir=tmp_dir,
    )
```

Note: `os` is already at module level in `instance_repository.py` — no local import needed. `Config` is imported locally inside the method to avoid a potential circular import at module level.

- [ ] **Step 5: Rewrite `snow_cli/config.py`**

Replace the entire file with:

```python
"""Runtime configuration value object."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """Immutable runtime configuration for a ServiceNow instance."""
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
```

- [ ] **Step 6: Update `snow_cli/cli.py`**

Change line 4 from:

```python
from .config import Config
```

to:

```python
from .instance_repository import InstanceRepository
```

Change line 26 from:

```python
config = Config(instance=instance)
```

to:

```python
config = InstanceRepository().load_config(instance=instance)
```

- [ ] **Step 7: Add explicit `mkdir` in `snow_cli/commands.py`**

Locate `_run_script_once` (around line 202). Find this block:

```python
    # Save raw output for debugging
    output_file = config.tmp_dir / "last_run_output.txt"
    fd = os.open(str(output_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
```

Replace with:

```python
    # Save raw output for debugging
    output_file = config.tmp_dir / "last_run_output.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(output_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
```

- [ ] **Step 8: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests **PASS**.

- [ ] **Step 9: Commit**

```bash
git add snow_cli/instance_repository.py snow_cli/config.py snow_cli/cli.py snow_cli/commands.py tests/test_instance_repository.py tests/test_commands.py
git commit -m "refactor: add InstanceRepository.load_config; rewrite Config as lean dataclass"
```

---

## Task 3: Update `snow_cli/instance_manager.py`

**Files:**
- Modify: `snow_cli/instance_manager.py`

The function signatures and printed output are unchanged — only the internal mechanism for loading/saving instances changes.

- [ ] **Step 1: Update the import and all call sites in `instance_manager.py`**

Replace the first line:

```python
from .config import Config
```

with:

```python
from .instance_repository import InstanceRepository
```

Then apply these substitutions throughout the file:

| Location | Before | After |
|---|---|---|
| `add_instance` (line ~30) | `config = Config()` | `repo = InstanceRepository()` |
| `add_instance` (line ~31) | `keyring_success = config.save_instance(instance, user, password, set_default)` | `keyring_success = repo.save(instance, user, password, set_default)` |
| `add_instance` (line ~42) | `if set_default or config.get_default_instance() == instance:` | `if set_default or repo.get_default() == instance:` |
| `list_instances` (line ~57) | `config = Config()` | `repo = InstanceRepository()` |
| `list_instances` (line ~58) | `instances = config.list_instances()` | `instances = repo.list_all()` |
| `list_instances` (line ~59) | `default = config.get_default_instance()` | `default = repo.get_default()` |
| `use_instance` (line ~82) | `config = Config()` | `repo = InstanceRepository()` |
| `use_instance` (line ~83) | `config.set_default_instance(instance)` | `repo.set_default(instance)` |
| `remove_instance` (line ~98) | `config = Config()` | `repo = InstanceRepository()` |
| `remove_instance` (line ~100) | `instances = config.list_instances()` | `instances = repo.list_all()` |
| `remove_instance` (line ~111) | `config.remove_instance(instance)` | `repo.remove(instance)` |
| `show_info` (line ~122) | `config = Config()` | `repo = InstanceRepository()` |
| `show_info` (line ~125–136) | `if config.instance:` / `config.cookie_file` / `config.get_default_instance()` | `config = repo.load_config()` before the block; keep `config.instance`, `config.cookie_file`; replace `config.get_default_instance()` with `repo.get_default()` |
| `show_info` (line ~140) | `instances = config.list_instances()` | `instances = repo.list_all()` |

The complete updated `show_info` function:

```python
def show_info():
    """Show current configuration"""
    repo = InstanceRepository()
    config = repo.load_config()

    if config.instance:
        print(f"Current instance: {config.instance}")
        print(f"  User: {config.user or '(not set)'}")
        print(f"  Password: {'(set)' if config.password else '(not set)'}")
        print(f"  Cookie file: {config.cookie_file}")
    else:
        default = repo.get_default()
        if default:
            print(f"Default instance: {default}")
        else:
            print("No instance configured.")

    print()

    instances = repo.list_all()
    if instances:
        print(f"Total instances configured: {len(instances)}")
        print("\nRun 'snow list' to see all instances.")
    else:
        print("No instances configured.")
        print("Run 'snow add' to add an instance.")

    return 0
```

- [ ] **Step 2: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests **PASS**.

- [ ] **Step 3: Commit**

```bash
git add snow_cli/instance_manager.py
git commit -m "refactor: update instance_manager to use InstanceRepository"
```

---

## Task 4: Replace `DummyConfig` with `Config(...)` across all tests

**Files:**
- Modify: `tests/test_commands.py`

`DummyConfig` was a duck-typed substitute for the old `Config` class. The new `Config` dataclass can be constructed directly in tests with explicit field values — no stub needed.

- [ ] **Step 1: Replace `DummyConfig` class definition and all usages**

Delete the entire `DummyConfig` class (lines 51–66):

```python
class DummyConfig:
    def __init__(self, tmp_path):
        self.instance = "dev1234.service-now.com"
        self._tmp_dir = Path(tmp_path)

    def ensure_instance_set(self):
        return None

    @property
    def tmp_dir(self):
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        return self._tmp_dir

    @property
    def cookie_file(self):
        return self.tmp_dir / "cookies.txt"
```

Add this import at the top of the test file (after the existing `from snow_cli import cli as cli_module` line):

```python
from snow_cli.config import Config
```

Replace each `DummyConfig(tmp_dir)` usage. The pattern is always:

```python
# Before
config = DummyConfig(tmp_dir)

# After
config = Config(
    instance="dev1234.service-now.com",
    cookie_file=Path(tmp_dir) / "cookies.txt",
    tmp_dir=Path(tmp_dir),
)
```

For `_make_config` helpers that also set `user` and `password`, pass them at construction:

```python
# Before
def _make_config(self, tmp_dir):
    config = DummyConfig(tmp_dir)
    config.user = "u"
    config.password = "p"
    return config

# After
def _make_config(self, tmp_dir):
    return Config(
        instance="dev1234.service-now.com",
        user="u",
        password="p",
        cookie_file=Path(tmp_dir) / "cookies.txt",
        tmp_dir=Path(tmp_dir),
    )
```

For `AggregateRecordsCliTests._make_config` which also patches `ensure_credentials_set`:

```python
# Before
def _make_config(self, tmp_dir):
    config = DummyConfig(tmp_dir)
    config.user = "u"
    config.password = "p"
    config.ensure_credentials_set = lambda: None
    return config

# After
def _make_config(self, tmp_dir):
    config = Config(
        instance="dev1234.service-now.com",
        user="u",
        password="p",
        cookie_file=Path(tmp_dir) / "cookies.txt",
        tmp_dir=Path(tmp_dir),
    )
    config.ensure_credentials_set = lambda: None
    return config
```

(Dataclasses are mutable by default, so instance attribute assignment still works.)

- [ ] **Step 2: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests **PASS**.

- [ ] **Step 3: Commit**

```bash
git add tests/test_commands.py
git commit -m "refactor: replace DummyConfig stub with direct Config(...) construction in tests"
```
