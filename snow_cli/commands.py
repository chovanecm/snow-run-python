"""ServiceNow command implementations"""
import re
import sys
import json
from typing import Optional
import html

from .config import Config
from .session import SnowSession


DISPLAY_VALUE_MAP = {
    "values": "false",
    "display": "true",
    "both": "all",
}


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

        records = _fetch_records(config, table, query, order_by, order_by_desc, fields, limit, display_values)

        if not records:
            print("No records found.")
            return 0

        selected_fields = _resolve_selected_fields(fields, records[0])
        _print_records(records, selected_fields, no_header, display_values)
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


def _print_records(records: list, fields: list, no_header: bool, display_values: str):
    if not no_header:
        print("\t".join(fields))
    for record in records:
        row = [_format_field_value(record.get(field), display_values) for field in fields]
        print("\t".join(row))
