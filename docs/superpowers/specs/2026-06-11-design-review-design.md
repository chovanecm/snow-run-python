# Design Review: GoF & Pragmatic Programmer Violations

**Date:** 2026-06-11  
**Scope:** Full codebase (`snow_cli/`)  
**Approach:** Fix in impact order; largest architectural findings documented for a future session.

---

## Session plan

**Implement now (this session):**
1. Finding 1 — CLI command duplication
2. Finding 4 — Strategy pattern for output formatters
3. Finding 5 — `_run_with_capture` duplication
4. Finding 6 — Silent exception swallowing

**Document for a future session:**
- Finding 2 — Two HTTP client patterns
- Finding 3 — Config SRP violation
- Finding 7 — Magic strings (format names)
- Finding 8 — `_parse_output_lines` state machine complexity

---

## Findings

### Finding 1 — DRY: CLI Command Duplication `[IMPLEMENT NOW]`

**Principle:** GoF Template Method violation; PP DRY  
**Location:** `cli.py` lines 131–333

`record search` and `r search` share identical Click decorator chains (34 lines each). Same duplication for `record count`/`r count` and `record aggregate`/`r aggregate`/`r a`. Approximately 100 lines of pure copy-paste.

**Risk:** Adding an option to one alias silently leaves the other behind. Already observed: `r aggregate` long form was added via a manual `add_command` workaround rather than a shared definition.

**Fix:** Define each command once as a standalone Click command object, then register it under both groups with `add_command`:

```python
search_cmd = click.command(name="search")(...decorators...)(fn)
record.add_command(search_cmd)
r_alias.add_command(search_cmd)
```

The `_record_search_impl` and `_record_aggregate_impl` dispatcher functions are eliminated entirely.

---

### Finding 2 — Orthogonality: Two HTTP Client Patterns `[FUTURE SESSION]`

**Principle:** GoF Facade; PP Orthogonality  
**Location:** `session.py`, `commands.py`

Two separate HTTP paths to ServiceNow exist side by side:
- `SnowSession` — cookie-based auth for scraping (`login`, `elevate`, `run_script`)
- Raw `requests.get(auth=(user, password))` — basic auth for REST API calls (`_fetch_records`, `_fetch_aggregate_records`, `_fetch_table_fields`, `_fetch_record_count`)

Cross-cutting concerns (timeouts, retries, proxy configuration, SSL verification) must be applied in two separate places. REST calls also import `requests` locally inside functions, a sign of incomplete module design.

**Fix:** Introduce a `ServiceNowClient` class that owns both auth modes and serves as the single HTTP entry point. All command functions receive a client instance rather than constructing their own transport.

---

### Finding 3 — SRP: `Config` Class Does Too Much `[FUTURE SESSION]`

**Principle:** PP Orthogonality; Single Responsibility  
**Location:** `config.py`

`Config` is simultaneously:
- A runtime property bag (`instance`, `user`, `password`)
- A file persistence layer (`save_instance`, `remove_instance`, `set_default_instance`, `list_instances`)
- A keyring manager (`_get_password_from_keyring`, `_set_password_in_keyring`, `_delete_password_from_keyring`)
- A path provider (`tmp_dir`, `cookie_file`)
- A validator (`ensure_instance_set`, `ensure_credentials_set`)

**Fix:** Split into `InstanceRepository` (CRUD: config file + keyring) and a lean `Config` (runtime property bag + `ensure_*` validators). `instance_manager.py` commands should interact with `InstanceRepository` directly.

---

### Finding 4 — Strategy Pattern: Output Formatters `[IMPLEMENT NOW]`

**Principle:** GoF Strategy; PP Open/Closed  
**Location:** `commands.py` lines 917–937

`_output_records` dispatches via an `if/elif` chain. Adding a new output format requires three coordinated edits: `FORMAT_CHOICES`, the dispatch chain, and the new `_output_*` function.

**Fix:** Replace the dispatch chain with a `_FORMATTERS` registry dict:

```python
_FORMATTERS: dict[str, Callable] = {
    "table": _output_table,
    "tsv":   _output_tsv,
    "csv":   _output_csv,
    "json":  _output_json,
    "xml":   _output_xml,
    "excel": _output_excel,
}
```

Adding a new format is one entry in one place. The `FORMAT_CHOICES` list derives from `_FORMATTERS.keys()` so it stays in sync automatically.

---

### Finding 5 — DRY: `_run_with_capture` Duplication `[IMPLEMENT NOW]`

**Principle:** PP DRY  
**Location:** `mcp_server.py` lines 55–88

`_run_with_capture(config, fn, *args, **kwargs)` and `_run_without_config_with_capture(fn, *args, **kwargs)` are the same 16-line function differing only in whether `config` is passed as the first positional argument. Any change to output formatting must be applied twice.

**Fix:** Merge into one function. Since `config` is always the first arg when present, it can simply be included in `*args`:

```python
def _run_with_capture(fn, *args, **kwargs) -> str:
    ...
    exit_code = fn(*args, **kwargs)
    ...
```

All call sites pass `config` explicitly: `_run_with_capture(login, config)`.

---

### Finding 6 — Silent Exception Swallowing `[IMPLEMENT NOW]`

**Principle:** PP Don't live with broken windows  
**Location:** `config.py:49–51`, `session.py:35–36`

```python
except (json.JSONDecodeError, KeyError) as e:
    pass  # Ignore corrupted config file
```

```python
except Exception as e:
    # If cookie file is corrupted, ignore and start fresh
    pass
```

A corrupted config file produces zero feedback. The user sees an unrelated "no instance configured" error with no hint that the config file is the cause.

**Fix:** Emit a `stderr` warning. The pattern is already established in `audit.py` (silent catch-all with an explicit comment explaining why it must never raise). Here the situation is different — the user *can* act on the information.

```python
except (json.JSONDecodeError, KeyError) as e:
    print(f"Warning: config file is corrupted and will be ignored ({e})", file=sys.stderr)
```

---

### Finding 7 — Magic Strings: Format Names `[FUTURE SESSION]`

**Principle:** PP Avoid magic strings  
**Location:** `commands.py`, `cli.py` throughout

`"table"`, `"tsv"`, `"csv"`, `"json"`, `"xml"`, `"excel"` appear as raw string literals. `FORMAT_CHOICES` is a plain list with no IDE completion or typo protection.

**Fix:** `class OutputFormat(str, Enum)` integrates cleanly with `click.Choice(list(OutputFormat))` and provides static analysis support.

---

### Finding 8 — Complex State Machine in `_parse_output_lines` `[FUTURE SESSION]`

**Principle:** PP Reduce cognitive load  
**Location:** `commands.py` lines 253–307

Three interleaved position counters (`stdout_position`, `start_index`, `end_index`) in a single pass make the branching hard to reason about, even with good test coverage. The function is correct but resistant to safe modification.

**Fix:** Refactor as an explicit state machine with named states (`BEFORE_START`, `IN_SCRIPT`, `AFTER_END`). Each state's handling becomes a self-contained branch.
