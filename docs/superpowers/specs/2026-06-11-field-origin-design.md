# Design: Field Origin (`defined_on`) for `snow table fields`

**Date:** 2026-06-11

## Goal

When listing fields for a ServiceNow table, show which table in the inheritance hierarchy **originally introduced** each field. For example, `install_status` on `u_dhl_ci_hw_server` originates from `cmdb` (the root ancestor), not from `u_dhl_ci_hw_server` itself.

## Background

`_fetch_table_fields` already walks the full table hierarchy via `_get_table_hierarchy` and queries `sys_dictionary` with `nameIN[all,parent,tables]` in a single request. The `name` column (which table each dictionary row belongs to) is already fetched and stored as `_table` in intermediate entries — it is only stripped from the return value at the deduplication step. No extra API calls are needed.

## Scope

- `_fetch_table_fields` — change dedup logic and return value
- `table_fields` (CLI) — add `defined_on` to the columns list
- `table_fields_json` — no change; inherits automatically
- All output formats (table, tsv, csv, json, xml, excel) — consistent; all route through `_output_records`

## Data Model

Each returned dict gains a `defined_on` key:

```
{field, label, type, references, defined_on}
```

`defined_on` holds the name of the **deepest ancestor** (furthest from the queried table) that has a `sys_dictionary` entry for this field. For fields defined only on the queried table itself, `defined_on` equals the queried table name.

## Deduplication Logic Change

Current: single-pass, tracks `(child_priority, child_entry)` per field — child wins (lowest hierarchy index).

New: single-pass, tracks `(child_priority, child_entry, ancestor_priority, origin_table)` per field:

- **child wins** for `field`, `label`, `type`, `references` (override/specialisation takes effect)
- **ancestor wins** for `defined_on` (deepest introducer in the hierarchy)

Both comparisons happen in one loop iteration per entry; no second pass.

Result construction:

```python
{**{k: v for k, v in child_entry.items() if k != "_table"}, "defined_on": origin_table}
```

## Output

Column order: `field | label | type | references | defined_on`

Example (`snow table fields u_dhl_ci_hw_server`, partial):

```
field            label    type     references  defined_on
install_status   Status   integer              cmdb
u_custom_field   Custom   string               u_dhl_ci_hw_server
```

## Testing

- Unit tests for `_fetch_table_fields`: mock `sys_dictionary` response with fields spanning multiple hierarchy levels; assert `defined_on` is the deepest ancestor for inherited fields and the table itself for native fields.
- Existing column assertions updated to include `defined_on`.
