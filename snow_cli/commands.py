"""ServiceNow command implementations"""
import csv
import io
import re
import sys
import json
from datetime import datetime
from typing import Optional
import html

from .config import Config
from .session import SnowSession


DISPLAY_VALUE_MAP = {
    "values": "false",
    "display": "true",
    "both": "all",
}

FORMAT_CHOICES = ["table", "tsv", "csv", "json", "xml", "excel"]


def login(config: Config) -> int:
    """Login to ServiceNow instance"""
    try:
        config.ensure_credentials_set()

        session = SnowSession(config.instance, config.cookie_file)

        # Get login token
        login_token = session.get_login_token()

        # Perform login
        response = session.post(
            "/login.do",
            data={
                "sysparm_ck": login_token,
                "user_name": config.user,
                "user_password": config.password,
                "ni.nolog.user_password": "true",
                "ni.noecho.user_name": "true",
                "ni.noecho.user_password": "true",
                "screensize": "1920x1080",
                "sys_action": "sysverb_login",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        if response.status_code == 200:
            print(f"Successfully logged in to {config.instance}")
            return 0
        else:
            print(f"Login failed with status code: {response.status_code}", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Login error: {e}", file=sys.stderr)
        return 1


def elevate(config: Config) -> int:
    """Elevate user privileges (e.g., security_admin role)"""
    try:
        config.ensure_instance_set()

        session = SnowSession(config.instance, config.cookie_file)

        # Get elevation token
        token = session.get_elevate_token()

        # Request role elevation
        response = session.post(
            "/api/now/ui/impersonate/role",
            headers={
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
                "X-WantSessionNotificationMessages": "true",
                "X-UserToken": token,
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json, text/plain, */*",
                "Connection": "keep-alive",
            },
            json={"roles": "security_admin"},
        )

        if response.status_code in (200, 201):
            print(f"Successfully elevated privileges on {config.instance}")
            return 0
        else:
            print(f"Elevation failed with status code: {response.status_code}", file=sys.stderr)
            print(f"Response: {response.text}", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Elevation error: {e}", file=sys.stderr)
        return 1


def run_script(config: Config, script_file: Optional[str] = None, script_content: Optional[str] = None) -> int:
    """Run a background script on ServiceNow"""
    try:
        config.ensure_instance_set()

        # Use provided content, or read from file/stdin
        if script_content is None:
            if script_file and script_file != "-":
                with open(script_file, "r") as f:
                    script_content = f.read()
            else:
                # Read from stdin
                script_content = sys.stdin.read()

        session = SnowSession(config.instance, config.cookie_file)

        # Get script execution token
        token = session.get_script_token()

        # Execute script
        response = session.post(
            "/sys.scripts.do",
            headers={
                "Connection": "keep-alive",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            },
            data={
                "sysparm_ck": token,
                "runscript": "Run script",
                "record_for_rollback": "on",
                "quota_managed_transaction": "on",
                "script": script_content,
            },
        )

        if response.status_code != 200:
            print(f"Script execution failed with status: {response.status_code}", file=sys.stderr)
            return 1

        # Save raw output for debugging
        output_file = config.tmp_dir / "last_run_output.txt"
        output_file.write_text(response.text)

        # Parse and display output
        _parse_and_display_output(response.text)
        return 0

    except FileNotFoundError:
        print(f"Script file not found: {script_file}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Script execution error: {e}", file=sys.stderr)
        return 1


def _parse_and_display_output(html_response: str):
    """Parse ServiceNow script output and display stdout/stderr separately"""
    # Extract script output from HTML
    # ServiceNow wraps output in <PRE> tags with markers like:
    # *** Script: (stdout content)
    # <BR/> (stderr content)

    stdout_parts = []
    stderr_parts = []

    # Find all <PRE> blocks
    pre_blocks = re.findall(r"<PRE>(.*?)</PRE>", html_response, re.DOTALL | re.IGNORECASE)

    for block in pre_blocks:
        # Decode HTML entities
        block = html.unescape(block)

        # Split by script markers
        # *** Script: indicates stdout
        # <BR/> indicates stderr
        parts = re.split(r"\*\*\* Script: |<BR/>|<br/>", block, flags=re.IGNORECASE)

        mode = None
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue

            # Alternate between stdout and stderr based on marker
            if "*** Script:" in block:
                # First part after *** Script: is stdout
                if i % 2 == 1:
                    stdout_parts.append(part)
                else:
                    stderr_parts.append(part)
            else:
                # If no script marker, treat as stderr
                stderr_parts.append(part)

    # Print stdout
    for line in stdout_parts:
        print(line)

    # Print stderr to stderr
    for line in stderr_parts:
        if line:
            print(line, file=sys.stderr)


def _fetch_records(
    config: Config,
    table: str,
    query: Optional[str] = None,
    order_by: Optional[list] = None,
    order_by_desc: Optional[list] = None,
    fields: Optional[str] = None,
    limit: Optional[int] = None,
    display_values: str = "both",
) -> list:
    """Fetch records from Table API and return as a list of dicts. Raises on error."""
    import requests as _requests

    query_parts = []
    if query:
        query_parts.append(query)
    if order_by:
        query_parts.extend([f"ORDERBY{field}" for field in order_by if field])
    if order_by_desc:
        query_parts.extend([f"ORDERBYDESC{field}" for field in order_by_desc if field])

    params = {
        "sysparm_display_value": DISPLAY_VALUE_MAP[display_values],
        "sysparm_query": "^".join(query_parts),
    }
    if fields:
        params["sysparm_fields"] = fields
    if limit is not None:
        params["sysparm_limit"] = str(limit)

    response = _requests.get(
        f"https://{config.instance}/api/now/table/{table}",
        params=params,
        headers={"Accept": "application/json"},
        auth=(config.user, config.password),
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Record query failed with status code: {response.status_code}\n{response.text}"
        )

    payload = response.json()
    records = payload.get("result", [])
    if isinstance(records, dict):
        records = [records]
    return records


def _get_table_hierarchy(base: str, auth: tuple, table_name: str) -> list:
    """Return list of table names from table_name up to the root (most-specific first)."""
    import requests as _requests
    hierarchy = []
    current = table_name
    visited = set()
    while current and current not in visited:
        visited.add(current)
        hierarchy.append(current)
        resp = _requests.get(
            f"{base}/api/now/table/sys_db_object",
            params={
                "sysparm_query": f"name={current}",
                "sysparm_fields": "super_class.name",
                "sysparm_limit": "1",
                "sysparm_display_value": "false",
            },
            auth=auth,
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            break
        rows = resp.json().get("result") or []
        if not rows:
            break
        parent = rows[0].get("super_class.name") or ""
        if isinstance(parent, dict):
            parent = parent.get("value") or parent.get("display_value") or ""
        current = parent.strip() if parent else ""
    return hierarchy


def _fetch_table_fields(config: Config, table_name: str) -> list:
    """Return all fields (including inherited) for a table. Raises on error.

    Each entry: {field, label, type, references}
    """
    import requests as _requests
    auth = (config.user, config.password)
    base = f"https://{config.instance}"

    hierarchy = _get_table_hierarchy(base, auth, table_name)
    if not hierarchy:
        raise RuntimeError(f"Table '{table_name}' not found or not accessible.")

    table_in_query = ",".join(hierarchy)
    resp = _requests.get(
        f"{base}/api/now/table/sys_dictionary",
        params={
            "sysparm_query": f"nameIN{table_in_query}^elementISNOTEMPTY",
            "sysparm_fields": "element,column_label,internal_type,reference,name",
            "sysparm_limit": "10000",
            "sysparm_display_value": "all",
            "sysparm_no_count": "true",
        },
        auth=auth,
        headers={"Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch fields (HTTP {resp.status_code}): {resp.text[:200]}"
        )

    raw = resp.json().get("result") or []

    def _val(cell):
        if isinstance(cell, dict):
            return cell.get("value") or ""
        return str(cell) if cell else ""

    # Build priority map: lower index in hierarchy = higher priority (child wins)
    table_priority = {t: i for i, t in enumerate(hierarchy)}

    # Collect all field entries
    entries = []
    for row in raw:
        field_name = _val(row.get("element"))
        if not field_name:
            continue
        entries.append({
            "_table": _val(row.get("name")),
            "field": field_name,
            "label": _val(row.get("column_label")),
            "type": _val(row.get("internal_type")),
            "references": _val(row.get("reference")),
        })

    # Deduplicate: child table definition wins over parent
    seen = {}
    for entry in entries:
        f = entry["field"]
        prio = table_priority.get(entry["_table"], len(hierarchy))
        if f not in seen or prio < seen[f][0]:
            seen[f] = (prio, entry)

    result = sorted(
        ({k: v for k, v in e.items() if k != "_table"} for _, e in seen.values()),
        key=lambda x: x["field"],
    )
    return result


def table_fields(
    config: Config,
    table_name: str,
    fmt: str = "table",
    output_file: Optional[str] = None,
) -> int:
    """Output all fields for a ServiceNow table (CLI output)."""
    try:
        config.ensure_credentials_set()
        if fmt not in FORMAT_CHOICES:
            print(f"Invalid format. Use one of: {', '.join(FORMAT_CHOICES)}", file=sys.stderr)
            return 1
        if fmt == "excel" and not output_file:
            print("--output FILE is required when --format is excel.", file=sys.stderr)
            return 1

        fields_data = _fetch_table_fields(config, table_name)
        if not fields_data:
            print(f"No fields found for table '{table_name}'.")
            return 0

        columns = ["field", "label", "type", "references"]
        if fmt == "json":
            _write_or_print(json.dumps(fields_data, ensure_ascii=False, indent=2), output_file)
        elif fmt == "xml":
            _write_or_print(_build_xml(fields_data, "sys_dictionary", "values"), output_file)
        else:
            _output_records(fields_data, columns, no_header=False, display_values="values",
                            fmt=fmt, output_file=output_file, table="sys_dictionary")
        return 0
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Table fields error: {e}", file=sys.stderr)
        return 1


def table_fields_json(config: Config, table_name: str) -> list:
    """Return all fields for a table as a list of dicts. Raises on error."""
    config.ensure_credentials_set()
    return _fetch_table_fields(config, table_name)


def search_records(
    config: Config,
    table: str,
    query: Optional[str] = None,
    order_by: Optional[list] = None,
    order_by_desc: Optional[list] = None,
    fields: Optional[str] = None,
    limit: Optional[int] = None,
    no_header: bool = False,
    sys_id: bool = False,
    display_values: str = "both",
    fmt: str = "table",
    output_file: Optional[str] = None,
) -> int:
    """Search records in a ServiceNow table using Table API (CLI output)."""
    try:
        config.ensure_credentials_set()

        if sys_id:
            fields = "sys_id"
            no_header = True

        if display_values not in DISPLAY_VALUE_MAP:
            print(
                "Invalid display values mode. Use one of: values, display, both.",
                file=sys.stderr,
            )
            return 1

        if fmt not in FORMAT_CHOICES:
            print(f"Invalid format. Use one of: {', '.join(FORMAT_CHOICES)}", file=sys.stderr)
            return 1

        if fmt == "excel" and not output_file:
            print("--output FILE is required when --format is excel.", file=sys.stderr)
            return 1

        records = _fetch_records(config, table, query, order_by, order_by_desc, fields, limit, display_values)

        if not records:
            if fmt not in ("json", "xml"):
                print("No records found.")
            elif fmt == "json":
                _write_or_print("[]", output_file)
            elif fmt == "xml":
                _write_or_print(_build_xml([], table, display_values), output_file)
            return 0

        selected_fields = _resolve_selected_fields(fields, records[0])
        _output_records(records, selected_fields, no_header, display_values, fmt, output_file, table)
        return 0
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    except json.JSONDecodeError:
        print("Failed to parse API response as JSON.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Record query error: {e}", file=sys.stderr)
        return 1


def search_records_json(
    config: Config,
    table: str,
    query: Optional[str] = None,
    order_by: Optional[list] = None,
    order_by_desc: Optional[list] = None,
    fields: Optional[str] = None,
    limit: Optional[int] = None,
    display_values: str = "both",
) -> list:
    """Search records and return as a list of dicts (for programmatic/MCP use). Raises on error."""
    config.ensure_credentials_set()
    if display_values not in DISPLAY_VALUE_MAP:
        raise ValueError(f"Invalid display_values '{display_values}'. Use one of: values, display, both.")
    return _fetch_records(config, table, query, order_by, order_by_desc, fields, limit, display_values)


def _resolve_selected_fields(fields: Optional[str], sample_record: dict) -> list:
    if fields:
        return [field.strip() for field in fields.split(",") if field.strip()]
    return list(sample_record.keys())


def _format_field_value(value, display_values: str) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        if display_values == "both":
            display = value.get("display_value", "")
            raw = value.get("value", "")
            if display == raw:
                return str(display)
            return f"{display} ({raw})"
        if display_values == "display":
            return str(value.get("display_value", ""))
        return str(value.get("value", ""))
    return str(value)


def _write_or_print(text: str, output_file: Optional[str]):
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Written to {output_file}")
    else:
        print(text)


def _output_records(
    records: list,
    fields: list,
    no_header: bool,
    display_values: str,
    fmt: str,
    output_file: Optional[str],
    table: str,
):
    if fmt == "table":
        _output_table(records, fields, no_header, display_values, output_file)
    elif fmt == "tsv":
        _output_tsv(records, fields, no_header, display_values, output_file)
    elif fmt == "csv":
        _output_csv(records, fields, no_header, display_values, output_file)
    elif fmt == "json":
        _write_or_print(json.dumps(records, ensure_ascii=False, indent=2), output_file)
    elif fmt == "xml":
        _write_or_print(_build_xml(records, table, display_values), output_file)
    elif fmt == "excel":
        _output_excel(records, fields, no_header, display_values, output_file)


def _output_table(records: list, fields: list, no_header: bool, display_values: str, output_file: Optional[str]):
    from tabulate import tabulate
    rows = [
        [_format_field_value(r.get(f), display_values) for f in fields]
        for r in records
    ]
    headers = [] if no_header else fields
    text = tabulate(rows, headers=headers, tablefmt="simple")
    _write_or_print(text, output_file)


def _output_tsv(records: list, fields: list, no_header: bool, display_values: str, output_file: Optional[str]):
    lines = []
    if not no_header:
        lines.append("\t".join(fields))
    for record in records:
        lines.append("\t".join(_format_field_value(record.get(f), display_values) for f in fields))
    _write_or_print("\n".join(lines), output_file)


def _output_csv(records: list, fields: list, no_header: bool, display_values: str, output_file: Optional[str]):
    buf = io.StringIO()
    writer = csv.writer(buf)
    if not no_header:
        writer.writerow(fields)
    for record in records:
        writer.writerow([_format_field_value(record.get(f), display_values) for f in fields])
    _write_or_print(buf.getvalue().rstrip("\r\n"), output_file)


def _build_xml(records: list, table: str, display_values: str) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    parts = [f'<?xml version="1.0" encoding="UTF-8"?>', f'<unload unload_date="{now}">']
    for record in records:
        parts.append(f'<{table} action="INSERT_OR_UPDATE">')
        for field_name, value in record.items():
            safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", field_name)
            if isinstance(value, dict):
                raw = str(value.get("value", "") or "")
                display = str(value.get("display_value", "") or "")
                if display_values == "display":
                    parts.append(f"  <{safe_name}>{html.escape(display)}</{safe_name}>")
                elif display_values == "values":
                    parts.append(f"  <{safe_name}>{html.escape(raw)}</{safe_name}>")
                else:  # both
                    if display and display != raw:
                        parts.append(f'  <{safe_name} display_value="{html.escape(display)}">{html.escape(raw)}</{safe_name}>')
                    else:
                        parts.append(f"  <{safe_name}>{html.escape(raw)}</{safe_name}>")
            else:
                parts.append(f"  <{safe_name}>{html.escape(str(value or ''))}</{safe_name}>")
        parts.append(f"</{table}>")
    parts.append("</unload>")
    return "\n".join(parts)


def _output_excel(records: list, fields: list, no_header: bool, display_values: str, output_file: str):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    row_offset = 0
    if not no_header:
        ws.append(fields)
        row_offset = 1
    for record in records:
        ws.append([_format_field_value(record.get(f), display_values) for f in fields])
    wb.save(output_file)
    print(f"Written to {output_file}")
