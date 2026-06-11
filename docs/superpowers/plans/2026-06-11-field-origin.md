# Field Origin (`defined_on`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `defined_on` column to `snow table fields` output showing which ancestor table originally introduced each field.

**Architecture:** The `_fetch_table_fields` function already fetches the `name` column from `sys_dictionary` (which table each row belongs to) and stores it as `_table` in intermediate entries — it then strips it. We extend the dedup loop to track both the effective (child-wins) entry and the origin (ancestor-wins) table, then include `defined_on` in every returned dict. The CLI column list gets one extra entry; all output formats follow automatically via `_output_records`.

**Tech Stack:** Python 3.11, requests, unittest/mock

---

### Task 1: Test and implement `defined_on` in `_fetch_table_fields`

**Files:**
- Modify: `snow_cli/commands.py:509-521` (dedup logic + result construction + docstring)
- Test: `tests/test_commands.py` (new `TableFieldsTests` class at end of file)

- [ ] **Step 1: Write the failing tests**

Add this class at the end of `tests/test_commands.py` (before the final `if __name__ == "__main__":` block if present, otherwise at end of file):

```python
class TableFieldsTests(unittest.TestCase):
    """Tests for _fetch_table_fields() — field origin tracking."""

    def _mock_response(self, payload, status=200):
        m = Mock()
        m.status_code = status
        m.json.return_value = payload
        m.text = ""
        return m

    def _hierarchy_side_effects(self, chain):
        """
        Build side-effect list for _get_table_hierarchy's sys_db_object calls.
        chain: ["child", "middle", "root"] produces:
          call 1: child -> middle
          call 2: middle -> root
          call 3: root -> no parent
        """
        effects = []
        for i, name in enumerate(chain):
            parent = chain[i + 1] if i + 1 < len(chain) else ""
            effects.append(self._mock_response({"result": [{"super_class.name": parent}]}))
        return effects

    def test_inherited_field_shows_deepest_ancestor(self):
        """install_status defined on child, middle, and root → defined_on is root."""
        from snow_cli.commands import _fetch_table_fields

        hier = ["child_table", "middle_table", "root_table"]
        dict_payload = {
            "result": [
                {"element": {"value": "install_status"}, "column_label": {"value": "Status"},
                 "internal_type": {"value": "integer"}, "reference": {"value": ""},
                 "name": {"value": "child_table"}},
                {"element": {"value": "install_status"}, "column_label": {"value": "Status"},
                 "internal_type": {"value": "integer"}, "reference": {"value": ""},
                 "name": {"value": "middle_table"}},
                {"element": {"value": "install_status"}, "column_label": {"value": "Status"},
                 "internal_type": {"value": "integer"}, "reference": {"value": ""},
                 "name": {"value": "root_table"}},
            ]
        }
        side_effects = self._hierarchy_side_effects(hier) + [self._mock_response(dict_payload)]

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = DummyConfig(tmp_dir)
            config.user = "u"
            config.password = "p"
            with patch("requests.get", side_effect=side_effects):
                fields = _fetch_table_fields(config, "child_table")

        f = next(x for x in fields if x["field"] == "install_status")
        self.assertEqual(f["defined_on"], "root_table")

    def test_native_field_shows_own_table(self):
        """Field defined only on queried table → defined_on equals queried table."""
        from snow_cli.commands import _fetch_table_fields

        hier = ["child_table", "parent_table"]
        dict_payload = {
            "result": [
                {"element": {"value": "u_custom"}, "column_label": {"value": "Custom"},
                 "internal_type": {"value": "string"}, "reference": {"value": ""},
                 "name": {"value": "child_table"}},
            ]
        }
        side_effects = self._hierarchy_side_effects(hier) + [self._mock_response(dict_payload)]

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = DummyConfig(tmp_dir)
            config.user = "u"
            config.password = "p"
            with patch("requests.get", side_effect=side_effects):
                fields = _fetch_table_fields(config, "child_table")

        f = next(x for x in fields if x["field"] == "u_custom")
        self.assertEqual(f["defined_on"], "child_table")

    def test_child_label_wins_over_parent(self):
        """When child overrides the label, the child label is used in output."""
        from snow_cli.commands import _fetch_table_fields

        hier = ["child_table", "parent_table"]
        dict_payload = {
            "result": [
                {"element": {"value": "state"}, "column_label": {"value": "Child Label"},
                 "internal_type": {"value": "integer"}, "reference": {"value": ""},
                 "name": {"value": "child_table"}},
                {"element": {"value": "state"}, "column_label": {"value": "Parent Label"},
                 "internal_type": {"value": "integer"}, "reference": {"value": ""},
                 "name": {"value": "parent_table"}},
            ]
        }
        side_effects = self._hierarchy_side_effects(hier) + [self._mock_response(dict_payload)]

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = DummyConfig(tmp_dir)
            config.user = "u"
            config.password = "p"
            with patch("requests.get", side_effect=side_effects):
                fields = _fetch_table_fields(config, "child_table")

        f = next(x for x in fields if x["field"] == "state")
        self.assertEqual(f["label"], "Child Label")   # child's label wins
        self.assertEqual(f["defined_on"], "parent_table")  # but origin is ancestor
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_commands.py::TableFieldsTests -v
```

Expected: 3 failures with `KeyError: 'defined_on'` (the key doesn't exist yet).

- [ ] **Step 3: Implement the change in `_fetch_table_fields`**

In `snow_cli/commands.py`, update the docstring on line 457 and the dedup block on lines 509–521:

**Docstring** (line 457):
```python
    Each entry: {field, label, type, references, defined_on}
```

**Dedup block** (replace lines 509–521):
```python
    # Deduplicate: child wins for effective field data; ancestor wins for defined_on
    seen = {}  # field → {"child_prio", "child_entry", "anc_prio", "origin"}
    for entry in entries:
        f = entry["field"]
        prio = table_priority.get(entry["_table"], len(hierarchy))
        if f not in seen:
            seen[f] = {"child_prio": prio, "child_entry": entry,
                       "anc_prio": prio, "origin": entry["_table"]}
        else:
            rec = seen[f]
            if prio < rec["child_prio"]:
                rec["child_prio"] = prio
                rec["child_entry"] = entry
            if prio > rec["anc_prio"]:
                rec["anc_prio"] = prio
                rec["origin"] = entry["_table"]

    result = sorted(
        (
            {**{k: v for k, v in rec["child_entry"].items() if k != "_table"},
             "defined_on": rec["origin"]}
            for rec in seen.values()
        ),
        key=lambda x: x["field"],
    )
    return result
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_commands.py::TableFieldsTests -v
```

Expected: 3 passed.

- [ ] **Step 5: Run the full suite to verify no regressions**

```bash
.venv/bin/python -m pytest tests/ -q
```

Expected: 42 passed (39 existing + 3 new).

- [ ] **Step 6: Commit**

```bash
git add snow_cli/commands.py tests/test_commands.py
git commit -m "feat: add defined_on to _fetch_table_fields — shows origin ancestor for each field"
```

---

### Task 2: Expose `defined_on` in CLI and all output formats

**Files:**
- Modify: `snow_cli/commands.py:545` (columns list in `table_fields`)

- [ ] **Step 1: Update the columns list**

In `snow_cli/commands.py`, find `table_fields` (around line 545):

```python
        columns = ["field", "label", "type", "references"]
```

Change to:

```python
        columns = ["field", "label", "type", "references", "defined_on"]
```

- [ ] **Step 2: Smoke-test the CLI manually**

```bash
.venv/bin/snow table fields u_dhl_ci_hw_server 2>&1 | head -5
```

Expected: header row includes `defined_on` as the 5th column, and `install_status` shows `cmdb` in that column.

- [ ] **Step 3: Run the full suite**

```bash
.venv/bin/python -m pytest tests/ -q
```

Expected: 42 passed.

- [ ] **Step 4: Commit**

```bash
git add snow_cli/commands.py
git commit -m "feat: show defined_on column in snow table fields output"
```
