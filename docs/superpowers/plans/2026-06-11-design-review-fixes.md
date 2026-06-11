# Design Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the four highest-impact code quality issues identified in the design review: CLI command duplication, output formatter dispatch, output-capture helper duplication, and silent exception swallowing.

**Architecture:** Four independent, sequential tasks — each ends with a commit, each task's tests must pass before starting the next. No new files are created; all changes are in-place edits to existing files.

**Tech Stack:** Python 3, Click, unittest/pytest

---

## File Map

| File | Task | Change |
|---|---|---|
| `snow_cli/cli.py` | 1 | Remove duplicated command definitions; define each command once with `@click.command`; register via `add_command` |
| `snow_cli/commands.py` | 2 | Add `_FORMATTERS` registry dict after `_output_excel`; replace `_output_records` if/elif chain; derive `FORMAT_CHOICES` from `_FORMATTERS` |
| `snow_cli/mcp_server.py` | 3 | Merge `_run_with_capture` and `_run_without_config_with_capture` into one function; update four call sites |
| `snow_cli/config.py` | 4 | Replace `pass` in except block with stderr warning |
| `snow_cli/session.py` | 4 | Replace `pass` in except block with stderr warning |
| `tests/test_commands.py` | 1, 2, 3, 4 | Add new test classes: `CliAliasParity`, `OutputFormatterRegistryTests`, `RunWithCaptureTests`, `SilentExceptionTests` |

---

## Task 1: Fix CLI Command Duplication

**Files:**
- Modify: `snow_cli/cli.py` (delete ~lines 94–337, replace with single definitions + `add_command` calls)
- Modify: `tests/test_commands.py` (add `CliAliasParity` class)

The three command pairs (`search`, `count`, `aggregate`) each have fully duplicated Click decorator chains. Delete the duplicate functions; define each command once with `@click.command`; register under both `record` and `r` groups via `add_command`. Also remove the now-unnecessary `_record_search_impl` and `_record_aggregate_impl` dispatcher functions.

- [ ] **Step 1: Write characterization tests**

These tests document that `r search` and `r count` forward options correctly. They pass today and must still pass after the refactoring.

Add this class to `tests/test_commands.py` (after the existing imports, before the first class):

```python
class CliAliasParity(unittest.TestCase):
    """Verify that record/r aliases are functionally identical."""

    def test_r_search_forwards_all_options(self):
        runner = CliRunner()
        fake_search = Mock(return_value=0)
        with patch.dict(sys.modules, {"keyring": keyring_stub}), \
             patch("snow_cli.cli.search_records", fake_search), \
             patch.object(cli_module.sys, "exit", side_effect=SystemExit):
            result = runner.invoke(
                cli_module.main,
                ["r", "search", "-q", "active=true", "-f", "sys_id,number",
                 "-l", "5", "incident"],
            )
        self.assertEqual(result.exit_code, 0)
        kw = fake_search.call_args.kwargs
        self.assertEqual(kw["query"], "active=true")
        self.assertEqual(kw["fields"], "sys_id,number")
        self.assertEqual(kw["limit"], 5)
        self.assertEqual(kw["table"], "incident")

    def test_r_count_forwards_query(self):
        runner = CliRunner()
        fake_count = Mock(return_value=0)
        with patch.dict(sys.modules, {"keyring": keyring_stub}), \
             patch("snow_cli.cli.count_records", fake_count), \
             patch.object(cli_module.sys, "exit", side_effect=SystemExit):
            result = runner.invoke(
                cli_module.main,
                ["r", "count", "-q", "active=true", "incident"],
            )
        self.assertEqual(result.exit_code, 0)
        # count_records is called as: count_records(config, table, query=query)
        self.assertEqual(fake_count.call_args.args[1], "incident")
        self.assertEqual(fake_count.call_args.kwargs.get("query"), "active=true")
```

- [ ] **Step 2: Run new tests to confirm they pass today**

```bash
python -m pytest tests/test_commands.py::CliAliasParity -v
```

Expected: both tests **PASS** (current code already supports these aliases — we are writing characterization tests).

- [ ] **Step 3: Refactor `cli.py`**

Delete the following from `cli.py` (keep everything else):
- `_record_search_impl` function (lines 94–110)
- `record_search` function and its decorators (lines 131–164)
- `r_search` function and its decorators (lines 167–200)
- `record_count` function and its decorators (lines 203–217)
- `r_count` function and its decorators (lines 220–226)
- `_record_aggregate_impl` function (lines 247–267)
- `record_aggregate` function and its decorators (lines 270–305)
- `r_aggregate` function and its decorators (lines 308–333)
- `r_alias.add_command(r_aggregate, name="aggregate")` line (line 337)

In their place, add the following block (between the `_add_aggregate_format_options` definition and the `@main.group(name="table")` block):

```python
@click.command(name="search")
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
def search_cmd(config, query, order_by, order_by_desc, fields, limit, no_header, sys_id, display_values, fmt, output_file, table_name):
    """Perform a query on a table."""
    sys.exit(
        search_records(
            config=config,
            table=table_name,
            query=query,
            order_by=list(order_by),
            order_by_desc=list(order_by_desc),
            fields=fields,
            limit=limit,
            no_header=no_header,
            sys_id=sys_id,
            display_values=display_values.lower(),
            fmt=fmt.lower(),
            output_file=output_file,
        )
    )


@click.command(name="count")
@click.option("-q", "--query", "query", help="Encoded query to filter records (sysparm_query)")
@click.argument("table_name")
@click.pass_obj
def count_cmd(config, query, table_name):
    """Count records in a table, optionally filtered by a query.

    Prints just the integer count.

    Examples:
      snow record count incident
      snow record count -q "active=true" incident
      snow record count -q "sys_created_on>=2024-01-01" incident
    """
    sys.exit(count_records(config, table_name, query=query))


@click.command(name="aggregate")
@click.option("-q", "--query", "query", help="Encoded query to filter records (sysparm_query)")
@click.option("-g", "--group-by", "group_by", multiple=True, help="Field to group by (can be used multiple times)")
@click.option("--count", "count", is_flag=True, help="Include COUNT in results")
@click.option("--avg", "avg", multiple=True, metavar="FIELD", help="Include AVG of FIELD (can be used multiple times)")
@click.option("--sum", "sum_fields", multiple=True, metavar="FIELD", help="Include SUM of FIELD (can be used multiple times)")
@click.option("--min", "min_fields", multiple=True, metavar="FIELD", help="Include MIN of FIELD (can be used multiple times)")
@click.option("--max", "max_fields", multiple=True, metavar="FIELD", help="Include MAX of FIELD (can be used multiple times)")
@click.option("--having", "having", help="HAVING clause filter (sysparm_having, e.g. COUNT>10)")
@click.option(
    "--display-values",
    type=click.Choice(["values", "display", "both"], case_sensitive=False),
    default="both",
    show_default=True,
    help="Return field values, display values, or both",
)
@_add_aggregate_format_options
@click.argument("table_name")
@click.pass_obj
def aggregate_cmd(config, query, group_by, count, avg, sum_fields, min_fields, max_fields,
                  having, display_values, fmt, output_file, table_name):
    """Aggregate records in a table using the ServiceNow Aggregate API.

    At least one of --count, --avg, --sum, --min, or --max must be provided.

    Examples:
      snow record aggregate --count incident
      snow record aggregate --count -g priority incident
      snow record aggregate --count -g category -q "active=true" incident
      snow record aggregate --count --avg reassignment_count -g priority incident
      snow r a --count -g state problem
    """
    sys.exit(
        aggregate_records(
            config=config,
            table=table_name,
            query=query,
            group_by=list(group_by) if group_by else None,
            count=count,
            avg=list(avg) if avg else None,
            sum_fields=list(sum_fields) if sum_fields else None,
            min_fields=list(min_fields) if min_fields else None,
            max_fields=list(max_fields) if max_fields else None,
            having=having,
            display_values=display_values.lower(),
            fmt=fmt.lower(),
            output_file=output_file,
        )
    )


record.add_command(search_cmd)
record.add_command(count_cmd)
record.add_command(aggregate_cmd)

r_alias.add_command(search_cmd)
r_alias.add_command(count_cmd)
r_alias.add_command(aggregate_cmd)
r_alias.add_command(aggregate_cmd, name="a")
```

- [ ] **Step 4: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: **ALL tests pass** (0 failures).

- [ ] **Step 5: Commit**

```bash
git add snow_cli/cli.py tests/test_commands.py
git commit -m "refactor: define CLI record/r commands once and register via add_command"
```

---

## Task 2: Strategy Pattern for Output Formatters

**Files:**
- Modify: `snow_cli/commands.py`
- Modify: `tests/test_commands.py`

Replace the `if/elif` dispatch chain in `_output_records` with a `_FORMATTERS` registry dict. `FORMAT_CHOICES` is redefined to derive from `_FORMATTERS.keys()` so the two stay automatically synchronized.

- [ ] **Step 1: Write a failing test**

This test imports `_FORMATTERS` — which doesn't exist yet — so it fails before the change.

Add to `tests/test_commands.py`:

```python
class OutputFormatterRegistryTests(unittest.TestCase):
    def test_formatters_dict_exists_and_covers_all_format_choices(self):
        from snow_cli.commands import FORMAT_CHOICES, _FORMATTERS
        self.assertEqual(set(FORMAT_CHOICES), set(_FORMATTERS.keys()))

    def test_format_choices_contains_all_expected_formats(self):
        from snow_cli.commands import FORMAT_CHOICES
        for fmt in ("table", "tsv", "csv", "json", "xml", "excel"):
            self.assertIn(fmt, FORMAT_CHOICES)
```

- [ ] **Step 2: Run to verify the first test fails**

```bash
python -m pytest tests/test_commands.py::OutputFormatterRegistryTests::test_formatters_dict_exists_and_covers_all_format_choices -v
```

Expected: **FAIL** with `ImportError: cannot import name '_FORMATTERS' from 'snow_cli.commands'`.

- [ ] **Step 3: Update `commands.py`**

**3a.** Remove the `FORMAT_CHOICES` constant from near the top of the file (currently line 25):

```python
FORMAT_CHOICES = ["table", "tsv", "csv", "json", "xml", "excel"]
```

**3b.** Replace the `_output_records` function (currently lines 917–937) with this slimmed version:

```python
def _output_records(
    records: list,
    fields: list,
    no_header: bool,
    display_values: str,
    fmt: str,
    output_file: Optional[str],
    table: str,
):
    _FORMATTERS[fmt](records, fields, no_header, display_values, output_file, table)
```

**3c.** After the `_output_excel` function (currently the last function in the file, around line 1008), add:

```python
_FORMATTERS = {
    "table": lambda r, f, nh, dv, of, t: _output_table(r, f, nh, dv, of),
    "tsv":   lambda r, f, nh, dv, of, t: _output_tsv(r, f, nh, dv, of),
    "csv":   lambda r, f, nh, dv, of, t: _output_csv(r, f, nh, dv, of),
    "json":  lambda r, f, nh, dv, of, t: _write_or_print(
                 json.dumps(r, ensure_ascii=False, indent=2), of),
    "xml":   lambda r, f, nh, dv, of, t: _write_or_print(_build_xml(r, t, dv), of),
    "excel": lambda r, f, nh, dv, of, t: _output_excel(r, f, nh, dv, of),
}
FORMAT_CHOICES = list(_FORMATTERS)
```

Lambda parameter names: `r`=records, `f`=fields, `nh`=no_header, `dv`=display_values, `of`=output_file, `t`=table.

> **Note:** `_output_records` now references `_FORMATTERS`, which is defined below it in the same module. This is fine — Python looks up names at call time, not at function-definition time. The `FORMAT_CHOICES` redefinition at the bottom overrides the one deleted in step 3a; all references to `FORMAT_CHOICES` inside function bodies will see the new value.

- [ ] **Step 4: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: **ALL tests pass**.

- [ ] **Step 5: Commit**

```bash
git add snow_cli/commands.py tests/test_commands.py
git commit -m "refactor: replace _output_records if/elif with _FORMATTERS registry dict"
```

---

## Task 3: Merge `_run_with_capture` Functions

**Files:**
- Modify: `snow_cli/mcp_server.py` (lines 55–88 + four call sites)
- Modify: `tests/test_commands.py` (add `RunWithCaptureTests` class)

Merge the two near-identical capture helpers into `_run_with_capture(fn, *args, **kwargs)`. The caller passes `config` as a regular positional argument (or omits it for functions that take no config).

- [ ] **Step 1: Write failing tests**

The first test calls `_run_with_capture(fn, config)` — the new signature. This fails today because the current signature is `_run_with_capture(config, fn)` (wrong order).

Add to `tests/test_commands.py`:

```python
class RunWithCaptureTests(unittest.TestCase):
    def test_captures_stdout_when_fn_takes_config(self):
        from snow_cli.mcp_server import _run_with_capture
        def fn_with_config(config):
            print(f"instance={config}")
            return 0
        result = _run_with_capture(fn_with_config, "my-instance")
        self.assertIn("instance=my-instance", result)

    def test_captures_stdout_when_fn_takes_no_args(self):
        from snow_cli.mcp_server import _run_with_capture
        def fn_no_config():
            print("no config needed")
            return 0
        result = _run_with_capture(fn_no_config)
        self.assertIn("no config needed", result)

    def test_stderr_output_is_prefixed(self):
        from snow_cli.mcp_server import _run_with_capture
        def fn():
            print("err line", file=sys.stderr)
            return 0
        result = _run_with_capture(fn)
        self.assertIn("[stderr]", result)
        self.assertIn("err line", result)

    def test_run_without_config_capture_no_longer_exists(self):
        import snow_cli.mcp_server as mcp
        self.assertFalse(hasattr(mcp, "_run_without_config_with_capture"))
```

- [ ] **Step 2: Run to verify the tests fail**

```bash
python -m pytest tests/test_commands.py::RunWithCaptureTests -v
```

Expected: `test_captures_stdout_when_fn_takes_config` **FAILS** (wrong arg order), `test_run_without_config_capture_no_longer_exists` **FAILS**.

- [ ] **Step 3: Replace the two functions in `mcp_server.py`**

Delete both `_run_with_capture` and `_run_without_config_with_capture` (lines 55–88) and replace with:

```python
def _run_with_capture(fn, *args, **kwargs) -> str:
    """Run a command function and return captured stdout + stderr as a single string."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        exit_code = fn(*args, **kwargs)
    output = stdout_buf.getvalue()
    errors = stderr_buf.getvalue()
    parts = []
    if output:
        parts.append(output.rstrip())
    if errors:
        parts.append(f"[stderr]\n{errors.rstrip()}")
    if not parts:
        parts.append("Done." if exit_code == 0 else f"Command failed (exit code {exit_code}).")
    return "\n".join(parts)
```

- [ ] **Step 4: Update the four call sites in `mcp_server.py`**

| Old call | New call |
|---|---|
| `_run_with_capture(config, run_script, script_content=script)` | `_run_with_capture(run_script, config, script_content=script)` |
| `_run_with_capture(config, login)` | `_run_with_capture(login, config)` |
| `_run_with_capture(config, elevate)` | `_run_with_capture(elevate, config)` |
| `_run_without_config_with_capture(list_instances)` | `_run_with_capture(list_instances)` |

- [ ] **Step 5: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: **ALL tests pass**.

- [ ] **Step 6: Commit**

```bash
git add snow_cli/mcp_server.py tests/test_commands.py
git commit -m "refactor: merge _run_with_capture and _run_without_config_with_capture"
```

---

## Task 4: Fix Silent Exception Swallowing

**Files:**
- Modify: `snow_cli/config.py` (lines 49–51)
- Modify: `snow_cli/session.py` (lines 34–36)
- Modify: `tests/test_commands.py` (add `SilentExceptionTests` class)

Replace bare `pass` in two `except` blocks with `stderr` warnings so users can diagnose corrupted files instead of receiving silent, confusing downstream errors.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_commands.py`. Note: `Config.__new__` bypasses `__init__` so we can inject a controlled path without patching `Path.home`.

```python
class SilentExceptionTests(unittest.TestCase):
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

    def test_corrupted_cookie_file_prints_warning_to_stderr(self):
        import requests as real_requests
        from snow_cli.session import SnowSession
        with tempfile.TemporaryDirectory() as tmp_dir:
            cookie_file = Path(tmp_dir) / "cookies.txt"
            cookie_file.write_text("this is not a mozilla cookie jar file")

            session = SnowSession.__new__(SnowSession)
            session.instance = "dev.service-now.com"
            session.base_url = "https://dev.service-now.com"
            session.cookie_file = cookie_file
            session.session = real_requests.Session()

            buf = io.StringIO()
            with redirect_stderr(buf):
                session._load_cookies()

            self.assertIn("Warning", buf.getvalue())
```

- [ ] **Step 2: Run to verify the tests fail**

```bash
python -m pytest tests/test_commands.py::SilentExceptionTests -v
```

Expected: both tests **FAIL** (no warning is currently printed).

- [ ] **Step 3: Fix `config.py`**

In `config.py`, locate the `except` block inside `_load_from_file` (around line 49):

```python
        except (json.JSONDecodeError, KeyError) as e:
            # Ignore corrupted config file
            pass
```

Replace with:

```python
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: config file is corrupted and will be ignored ({e})", file=sys.stderr)
```

- [ ] **Step 4: Fix `session.py`**

In `session.py`, locate the `except` block inside `_load_cookies` (around line 34):

```python
            except Exception as e:
                # If cookie file is corrupted, ignore and start fresh
                pass
```

Replace with:

```python
            except Exception as e:
                print(f"Warning: cookie file could not be loaded and will be ignored ({e})", file=sys.stderr)
```

- [ ] **Step 5: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: **ALL tests pass**.

- [ ] **Step 6: Commit**

```bash
git add snow_cli/config.py snow_cli/session.py tests/test_commands.py
git commit -m "fix: warn to stderr when config or cookie file cannot be loaded"
```
