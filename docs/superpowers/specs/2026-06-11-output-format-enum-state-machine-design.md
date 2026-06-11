# Design: OutputFormat Enum + _ParseState State Machine

**Date:** 2026-06-11
**Findings addressed:** Finding 7 (magic strings), Finding 8 (_parse_output_lines complexity)

---

## Finding 7 — `OutputFormat` Enum

### Problem

Three separate sources of truth define the valid output formats:

1. `_FORMATTERS` dict keys in `commands.py` — the actual authoritative list
2. `FORMAT_CHOICES = list(_FORMATTERS)` in `commands.py` — derived correctly
3. `AGGREGATE_FORMAT_CHOICES = ["table", "tsv", "csv", "json"]` in `commands.py` — a separate hardcoded list
4. `click.Choice(["table", "tsv", "csv", "json", "xml", "excel"])` in `cli.py` — hardcoded, not referencing `FORMAT_CHOICES`

`cli.py` already drifted from `commands.py` — adding a new format to `_FORMATTERS` would not be picked up by the CLI's `click.Choice`. Magic string comparisons (`fmt == "excel"`, `fmt not in ("json", "xml")`) are scattered through `commands.py`.

### Solution

Define `OutputFormat(str, Enum)` in `commands.py`. Because it inherits from `str`, enum members are strings — `hash(OutputFormat.TABLE) == hash("table")` — so the existing `_FORMATTERS` dict lookup continues to work without modification.

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
    def aggregate_choices(cls) -> list["OutputFormat"]:
        return [f for f in cls if f not in {cls.XML, cls.EXCEL}]
```

`__str__` returns the value so `click.Choice(list(OutputFormat))` displays `table/tsv/csv/json/xml/excel` (not `OutputFormat.TABLE`). Compatible with Python 3.8+.

### Changes

| File | Before | After |
|------|--------|-------|
| `commands.py` | `AGGREGATE_FORMAT_CHOICES = ["table", "tsv", "csv", "json"]` | `OutputFormat.aggregate_choices()` |
| `commands.py` | `FORMAT_CHOICES = list(_FORMATTERS)` | `FORMAT_CHOICES = list(OutputFormat)` |
| `commands.py` | `fmt == "excel"` etc. | `fmt == OutputFormat.EXCEL` etc. |
| `cli.py` | `click.Choice(["table", "tsv", "csv", "json", "xml", "excel"])` | `click.Choice(list(OutputFormat))` |
| `cli.py` | `click.Choice(["table", "tsv", "csv", "json"])` | `click.Choice(OutputFormat.aggregate_choices())` |

`_FORMATTERS` key type can stay as `str` — the lookup works either way due to `str` inheritance. No caller changes required; the function signatures remain `fmt: str`.

---

## Finding 8 — `_ParseState` State Machine

### Problem

`_parse_output_lines` in `commands.py` uses three interleaved counters (`stdout_position`, `start_index`, `end_index`) in a single pass. The branching is correct and well-tested, but the implicit state makes the routing logic hard to reason about when modifying it.

### Solution

Introduce a private `_ParseState(Enum)` with four named states. Initial state is derived once from `start_index` before the loop; transitions happen at marker positions inside the loop.

```python
from enum import Enum, auto

class _ParseState(Enum):
    PASSTHROUGH  = auto()  # no markers; all stdout → filtered_stdout
    BEFORE_START = auto()  # waiting for start_index; discard stdout
    IN_SCRIPT    = auto()  # between markers; stdout → filtered_stdout
    AFTER_END    = auto()  # past end marker; discard stdout
```

Loop structure:

```python
state = _ParseState.PASSTHROUGH if start_index is None else _ParseState.BEFORE_START
stdout_position = -1

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
```

The warning block after the loop is unchanged. Function signature and return type are identical — all existing tests pass without modification.

### State transition table

| State | Condition | Action | Next state |
|-------|-----------|--------|-----------|
| `PASSTHROUGH` | any stdout | → filtered_stdout | `PASSTHROUGH` |
| `BEFORE_START` | `pos < start_index` | → filtered_stderr | `BEFORE_START` |
| `BEFORE_START` | `pos == start_index` | skip (marker line) | `IN_SCRIPT` or `PASSTHROUGH` |
| `IN_SCRIPT` | `pos < end_index` | → filtered_stdout | `IN_SCRIPT` |
| `IN_SCRIPT` | `pos == end_index` | skip (marker line) | `AFTER_END` |
| `AFTER_END` | any stdout | → filtered_stderr | `AFTER_END` |

---

## Scope

- No new files
- No changes to function signatures or return types
- No changes to tests (behaviour is identical)
- `_ParseState` is module-private (underscore prefix)
- `OutputFormat` is exported (no underscore) — it is the public contract for format names
