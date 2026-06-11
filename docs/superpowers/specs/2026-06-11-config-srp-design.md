# Design: Config SRP Split

**Date:** 2026-06-11
**Finding:** F3 from `2026-06-11-design-review-design.md`
**Principle:** PP Orthogonality; Single Responsibility

---

## Problem

`Config` (`snow_cli/config.py`, 215 lines) has five distinct responsibilities:

1. Runtime property bag (`instance`, `user`, `password`)
2. File persistence (`save_instance`, `remove_instance`, `set_default_instance`, `list_instances`)
3. Keyring manager (`_get_password_from_keyring`, `_set_password_in_keyring`, `_delete_password_from_keyring`)
4. Path provider (`snow_dir`, `config_file`, `tmp_dir`, `cookie_file`)
5. Validator (`ensure_instance_set`, `ensure_credentials_set`)
6. Bootstrap loader (`__init__`, `_load_from_file`)

Adding a new storage backend or changing the config file location requires understanding all six concerns at once.

---

## Solution

Split into two units with one clear purpose each:

- **`InstanceRepository`** (`snow_cli/instance_repository.py`) — owns all file-system and keyring I/O, path computation, and bootstrap logic.
- **`Config`** (`snow_cli/config.py`) — a lean dataclass: runtime values + validators. No I/O, no paths, no side effects.

---

## `InstanceRepository`

```python
class InstanceRepository:
    def __init__(self, snow_dir: Path = Path.home() / ".snow-run"):
        self.snow_dir = snow_dir
        self.config_file = snow_dir / "config.json"

    # Factory — only public path to a Config
    def load_config(self, instance: Optional[str] = None) -> Config: ...

    # CRUD
    def save(self, instance: str, user: str, password: str, set_default: bool = False) -> bool: ...
    def remove(self, instance: str): ...
    def list_all(self) -> Dict[str, Dict]: ...
    def get_default(self) -> Optional[str]: ...
    def set_default(self, instance: str): ...

    # Path helpers
    def cookie_file_for(self, instance: str) -> Path: ...
    def tmp_dir_for(self, instance: str) -> Path: ...

    # Private
    def _load_json(self) -> dict: ...
    def _save_json(self, data: dict): ...
    def _get_password_from_keyring(self, instance: str, user: str) -> Optional[str]: ...
    def _set_password_in_keyring(self, instance: str, user: str, password: str) -> bool: ...
    def _delete_password_from_keyring(self, instance: str, user: str): ...
```

`load_config` is the sole factory for `Config`. Priority chains:
- Instance: `instance` argument > `snow_instance` env var > JSON file's `default_instance`
- User: `snow_user` env var > config file
- Password: `snow_pwd` env var > keyring > config file (legacy fallback)

It computes `cookie_file` and `tmp_dir` from the resolved instance (`None` for both when instance is `None`) and returns a populated `Config`.

`_load_json` is extracted to eliminate the repeated `open(config_file)` pattern across CRUD methods. Returns `{}` when the file does not exist; prints a warning to stderr and returns `{}` on `json.JSONDecodeError`.

`_save_json` writes with `os.open(..., 0o600)` — the secure write pattern already present in the current code, extracted once.

Corrupted-file warnings (currently in `Config._load_from_file`) move into `load_config` / `_load_json` as before.

---

## `Config` (lean dataclass)

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class Config:
    instance: Optional[str]
    user: Optional[str]
    password: Optional[str]
    cookie_file: Optional[Path]   # None when instance is None
    tmp_dir: Optional[Path]       # None when instance is None

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

No properties, no I/O, no directory creation. `cookie_file` and `tmp_dir` are set by `InstanceRepository.load_config()` from the resolved instance.

---

## Call-site changes

### `snow_cli/cli.py`

```python
# before
config = Config(instance=instance)

# after
config = InstanceRepository().load_config(instance=instance)
```

### `snow_cli/instance_manager.py`

Replace `from .config import Config` with `from .instance_repository import InstanceRepository`.

| Before | After |
|---|---|
| `config = Config()` | `repo = InstanceRepository()` |
| `config.save_instance(...)` | `repo.save(...)` |
| `config.list_instances()` | `repo.list_all()` |
| `config.get_default_instance()` | `repo.get_default()` |
| `config.set_default_instance(x)` | `repo.set_default(x)` |
| `config.remove_instance(x)` | `repo.remove(x)` |

`show_info` calls `repo.load_config()` to get a `Config` and displays `config.cookie_file` as before.

### `snow_cli/commands.py`

No import changes. `config.cookie_file` and `config.tmp_dir` remain valid field accesses on the dataclass.

One addition at `_run_script_once` (line 202), before the `os.open` call:

```python
output_file = config.tmp_dir / "last_run_output.txt"
output_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
```

The `tmp_dir` property previously created the directory on access. Now that it is a plain `Path` field, the caller creates it.

### `snow_cli/mcp_server.py`

No changes.

---

## Test changes

`SilentExceptionTests.test_corrupted_config_file_prints_warning_to_stderr` currently uses `Config.__new__` to inject a path without invoking `__init__`. After the refactor, the test uses `InstanceRepository` directly — no bypass needed:

```python
repo = InstanceRepository(snow_dir=Path(tmp_dir) / ".snow-run")
with redirect_stderr(buf):
    repo.load_config()
self.assertIn("Warning", buf.getvalue())
```

`DummyConfig` in the test file has `tmp_dir` as a mkdir-on-access property and `cookie_file` derived from it. After the refactor, all test classes that currently use `DummyConfig` (`RunScriptTests`, `AggregateFetchTests`, `AggregateRecordsTests`, `SearchRecordsTests`, `TableFieldsTests`, etc.) switch to constructing `Config(instance=..., user=..., password=..., cookie_file=..., tmp_dir=...)` directly. The `_run_script_once` call site gains an explicit `mkdir`, so `tmp_dir` no longer needs to be a mkdir-on-access property.

---

## File map

| File | Change |
|---|---|
| `snow_cli/instance_repository.py` | **New** — all persistence + path + bootstrap logic |
| `snow_cli/config.py` | **Rewrite** — lean dataclass, ~20 lines |
| `snow_cli/cli.py` | 1-line change: use `InstanceRepository().load_config()` |
| `snow_cli/instance_manager.py` | Import swap + method renames |
| `snow_cli/commands.py` | Add one `mkdir` in `_run_script_once` |
| `tests/test_commands.py` | Update `SilentExceptionTests`; replace `DummyConfig` with direct `Config(...)` across all test classes |
