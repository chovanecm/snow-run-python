# OutputFormat Enum + _ParseState State Machine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace magic format strings with a typed `OutputFormat` enum and make `_parse_output_lines` readable by converting its implicit counter logic to an explicit `_ParseState` state machine.

**Architecture:** `OutputFormat(str, Enum)` lives in `commands.py` alongside `_FORMATTERS`; `cli.py` imports it to drive `click.Choice`. `_ParseState` is a private module-level enum in `commands.py` used only inside `_parse_output_lines`. No new files. No signature changes.

**Tech Stack:** Python 3.8+ `enum.Enum`, Click

---

## File Map

| File | Changes |
|------|---------|
| `snow_cli/commands.py` | Add `OutputFormat` enum + `_ParseState` enum; update `FORMAT_CHOICES`, `AGGREGATE_FORMAT_CHOICES`, magic string comparisons, `_parse_output_lines` body |
| `snow_cli/cli.py` | Import `OutputFormat`; replace hardcoded `click.Choice([...])` lists |
| `tests/test_commands.py` | Add `OutputFormatEnumTests` class |

---

## Task 1: Define `OutputFormat` enum and add tests

**Files:**
- Modify: `tests/test_commands.py` (add test class)
- Modify: `snow_cli/commands.py` (add enum + update `FORMAT_CHOICES`)

- [ ] **Step 1: Write the failing tests**

Add this class at the bottom of `tests/test_commands.py` (after `OutputFormatterRegistryTests`):

```python
class OutputFormatEnumTests(unittest.TestCase):
    def test_enum_members_match_expected_formats(self):
        from snow_cli.commands import OutputFormat
        values = {f.value for f in OutputFormat}
        self.assertEqual(values, {"table", "tsv", "csv", "json", "xml", "excel"})

    def test_str_returns_value_not_member_name(self):
        from snow_cli.commands import OutputFormat
        self.assertEqual(str(OutputFormat.TABLE), "table")
        self.assertEqual(str(OutputFormat.EXCEL), "excel")

    def test_aggregate_choices_excludes_xml_and_excel(self):
        from snow_cli.commands import OutputFormat
        choices = OutputFormat.aggregate_choices()
        values = [str(f) for f in choices]
        self.assertEqual(sorted(values), ["csv", "json", "table", "tsv"])

    def test_string_membership_works_for_plain_strings(self):
        from snow_cli.commands import OutputFormat
        self.assertIn("table", list(OutputFormat))
        self.assertIn("excel", list(OutputFormat))
        self.assertNotIn("parquet", list(OutputFormat))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_commands.py::OutputFormatEnumTests -v
```

Expected: FAIL with `ImportError: cannot import name 'OutputFormat'`

- [ ] **Step 3: Add `OutputFormat` to `commands.py`**

Add `from enum import Enum` to the imports at the top of `snow_cli/commands.py` (after the existing stdlib imports, before the `.config` import):

```python
from enum import Enum
```

Then insert the `OutputFormat` class immediately after the module-level constants block (after `BR_TAG_RE = ...`, before `def login`):

```python
class OutputFormat(str, Enum):
    TABLE = "table"
    TSV   = "tsv"
    CSV   = "csv"
    JSON  = "json"
    XML   = "xml"
    EXCEL = "excel"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def aggregate_choices(cls) -> list:
        return [f for f in cls if f not in {cls.XML, cls.EXCEL}]
```

- [ ] **Step 4: Update `FORMAT_CHOICES` to derive from the enum**

At the bottom of `commands.py`, replace:

```python
FORMAT_CHOICES = list(_FORMATTERS)
```

with:

```python
FORMAT_CHOICES = list(OutputFormat)
```

- [ ] **Step 5: Run the new tests and the existing registry tests**

```bash
python -m pytest tests/test_commands.py::OutputFormatEnumTests tests/test_commands.py::OutputFormatterRegistryTests -v
```

Expected: all PASS. The registry test `test_formatters_dict_exists_and_covers_all_format_choices` still passes because `"table" == OutputFormat.TABLE` via str equality.

- [ ] **Step 6: Commit**

```bash
git add snow_cli/commands.py tests/test_commands.py
git commit -m "refactor: add OutputFormat str enum; derive FORMAT_CHOICES from it"
```

---

## Task 2: Replace `AGGREGATE_FORMAT_CHOICES` and magic string comparisons in `commands.py`

**Files:**
- Modify: `snow_cli/commands.py`

- [ ] **Step 1: Remove `AGGREGATE_FORMAT_CHOICES` and replace its usages**

In `commands.py`, delete this line (currently near line 692):

```python
AGGREGATE_FORMAT_CHOICES = ["table", "tsv", "csv", "json"]
```

Replace the two usages of `AGGREGATE_FORMAT_CHOICES`:

```python
# line ~729 — before:
if fmt not in AGGREGATE_FORMAT_CHOICES:
    print(
        f"Invalid format. Use one of: {', '.join(AGGREGATE_FORMAT_CHOICES)}",
        file=sys.stderr,
    )

# after:
if fmt not in OutputFormat.aggregate_choices():
    print(
        f"Invalid format. Use one of: {', '.join(str(f) for f in OutputFormat.aggregate_choices())}",
        file=sys.stderr,
    )
```

- [ ] **Step 2: Replace magic string comparisons**

In `aggregate_records` (near line 751):

```python
# before:
if fmt == "json":
    _write_or_print("[]", output_file)

# after:
if fmt == OutputFormat.JSON:
    _write_or_print("[]", output_file)
```

In `search_records` (near lines 835, 842–847):

```python
# before:
if fmt == "excel" and not output_file:
    ...
if fmt not in ("json", "xml"):
    print("No records found.")
elif fmt == "json":
    _write_or_print("[]", output_file)
elif fmt == "xml":
    _write_or_print(_build_xml([], table, display_values), output_file)

# after:
if fmt == OutputFormat.EXCEL and not output_file:
    ...
if fmt not in {OutputFormat.JSON, OutputFormat.XML}:
    print("No records found.")
elif fmt == OutputFormat.JSON:
    _write_or_print("[]", output_file)
elif fmt == OutputFormat.XML:
    _write_or_print(_build_xml([], table, display_values), output_file)
```

In `table_fields` (near line 549):

```python
# before:
if fmt == "excel" and not output_file:

# after:
if fmt == OutputFormat.EXCEL and not output_file:
```

- [ ] **Step 3: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add snow_cli/commands.py
git commit -m "refactor: replace AGGREGATE_FORMAT_CHOICES and magic format strings with OutputFormat enum"
```

---

## Task 3: Update `cli.py` to use `OutputFormat`

**Files:**
- Modify: `snow_cli/cli.py`

- [ ] **Step 1: Import `OutputFormat` in `cli.py`**

In `snow_cli/cli.py`, update the import from commands:

```python
# before:
from .commands import login, elevate, run_script, search_records, table_fields, count_records, aggregate_records

# after:
from .commands import login, elevate, run_script, search_records, table_fields, count_records, aggregate_records, OutputFormat
```

- [ ] **Step 2: Replace hardcoded `click.Choice` lists**

Replace `_FORMAT_OPTION` (near line 94):

```python
# before:
_FORMAT_OPTION = [
    click.option(
        "-F", "--format", "fmt",
        type=click.Choice(["table", "tsv", "csv", "json", "xml", "excel"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format",
    ),
    click.option("-O", "--output", "output_file", default=None, help="Write output to FILE (required for excel)"),
]

# after:
_FORMAT_OPTION = [
    click.option(
        "-F", "--format", "fmt",
        type=click.Choice(list(OutputFormat), case_sensitive=False),
        default=OutputFormat.TABLE,
        show_default=True,
        help="Output format",
    ),
    click.option("-O", "--output", "output_file", default=None, help="Write output to FILE (required for excel)"),
]
```

Replace `_AGGREGATE_FORMAT_OPTION` (near line 112):

```python
# before:
_AGGREGATE_FORMAT_OPTION = [
    click.option(
        "-F", "--format", "fmt",
        type=click.Choice(["table", "tsv", "csv", "json"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format",
    ),
    click.option("-O", "--output", "output_file", default=None, help="Write output to FILE"),
]

# after:
_AGGREGATE_FORMAT_OPTION = [
    click.option(
        "-F", "--format", "fmt",
        type=click.Choice(OutputFormat.aggregate_choices(), case_sensitive=False),
        default=OutputFormat.TABLE,
        show_default=True,
        help="Output format",
    ),
    click.option("-O", "--output", "output_file", default=None, help="Write output to FILE"),
]
```

- [ ] **Step 3: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 4: Smoke-test the CLI help output**

```bash
python -m snow_cli.cli record search --help
python -m snow_cli.cli r aggregate --help
```

Expected: `--format` shows `[table|tsv|csv|json|xml|excel]` for search and `[table|tsv|csv|json]` for aggregate.

- [ ] **Step 5: Commit**

```bash
git add snow_cli/cli.py
git commit -m "refactor: use OutputFormat enum in cli.py click.Choice options"
```

---

## Task 4: Refactor `_parse_output_lines` with `_ParseState` state machine

**Files:**
- Modify: `snow_cli/commands.py`

The existing tests in `ParseOutputLinesTests` cover all four cases (markers present, missing end marker, missing start marker, no markers). They will verify the refactor preserves behaviour without any test changes.

- [ ] **Step 1: Run existing parse output tests to establish baseline**

```bash
python -m pytest tests/test_commands.py -k "parse" -v
```

Expected: all PASS. Note the test names — they must all pass again after the refactor.

- [ ] **Step 2: Add `_ParseState` enum to `commands.py`**

Add `auto` to the enum import at the top of `commands.py`:

```python
from enum import Enum, auto
```

Insert `_ParseState` immediately before `_parse_output_lines` (the function currently near line 252):

```python
class _ParseState(Enum):
    PASSTHROUGH  = auto()
    BEFORE_START = auto()
    IN_SCRIPT    = auto()
    AFTER_END    = auto()
```

- [ ] **Step 3: Replace the loop body in `_parse_output_lines`**

Replace the entire body of `_parse_output_lines` (from `events = ...` through `return filtered_stdout, filtered_stderr`) with:

```python
def _parse_output_lines(
    html_response: str,
    start_marker: Optional[str] = None,
    end_marker: Optional[str] = None,
) -> Tuple[List[str], List[str]]:
    events = _extract_output_events(html_response)
    stdout_lines = [text for channel, text in events if channel == "stdout"]
    start_index, end_index = _find_marker_indexes(stdout_lines, start_marker, end_marker)

    state = _ParseState.PASSTHROUGH if start_index is None else _ParseState.BEFORE_START
    stdout_position = -1
    filtered_stdout: List[str] = []
    filtered_stderr: List[str] = []

    for channel, text in events:
        if channel != "stdout":
            filtered_stderr.append(text)
            continue

        stdout_position += 1

        if state == _ParseState.PASSTHROUGH:
            filtered_stdout.append(text)

        elif state == _ParseState.BEFORE_START:
            if stdout_position == start_index:
                state = _ParseState.IN_SCRIPT if end_index is not None else _ParseState.PASSTHROUGH
            else:
                filtered_stderr.append(text)

        elif state == _ParseState.IN_SCRIPT:
            if stdout_position == end_index:
                state = _ParseState.AFTER_END
            else:
                filtered_stdout.append(text)

        elif state == _ParseState.AFTER_END:
            filtered_stderr.append(text)

    if start_marker and end_marker:
        if start_index is None and end_marker in stdout_lines:
            filtered_stderr.append(
                "Warning: ServiceNow output start marker was not found; showing best-effort stdout."
            )
        elif start_index is not None and end_index is None:
            filtered_stderr.append(
                "Warning: ServiceNow output end marker was not found; showing best-effort stdout."
            )

    return filtered_stdout, filtered_stderr
```

- [ ] **Step 4: Run all parse output tests**

```bash
python -m pytest tests/test_commands.py -k "parse" -v
```

Expected: all PASS with identical results to Step 1.

- [ ] **Step 5: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add snow_cli/commands.py
git commit -m "refactor: replace _parse_output_lines counter logic with explicit _ParseState state machine"
```
