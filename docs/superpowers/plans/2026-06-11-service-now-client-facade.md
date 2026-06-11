# ServiceNowClient Facade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce `ServiceNowClient` as the single HTTP entry point for all ServiceNow communication, absorbing `SnowSession` and centralising all `requests` usage.

**Architecture:** Three sequential tasks, each ending with a green test suite and a commit. Task 1 creates the new client in isolation. Task 2 migrates the cookie/scraping path and deletes `session.py`. Task 3 migrates the REST path.

**Tech Stack:** Python 3, `requests`, `http.cookiejar`, unittest/pytest

---

## File Map

| File | Action | Change |
|---|---|---|
| `snow_cli/client.py` | **Create** | `ServiceNowClient` + `ScriptTokenError` |
| `snow_cli/session.py` | **Delete** | Absorbed into `client.py` |
| `snow_cli/commands.py` | **Modify** | Import swap; scraping and REST helpers use `ServiceNowClient` |
| `tests/test_client.py` | **Create** | Unit tests for `ServiceNowClient` |
| `tests/test_commands.py` | **Modify** | Mock target changes from `SnowSession`→`ServiceNowClient`; `requests.get` patches → mock client |

---

## Task 1: Create `snow_cli/client.py`

**Files:**
- Create: `snow_cli/client.py`
- Create: `tests/test_client.py`

No changes to `commands.py` or `session.py` yet — both still work as before after this task.

- [ ] **Step 1: Create `tests/test_client.py` with failing tests**

```python
import http.cookiejar
import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import Mock, patch

keyring_stub = types.SimpleNamespace(
    get_password=lambda *a, **kw: None,
    set_password=lambda *a, **kw: None,
    delete_password=lambda *a, **kw: None,
)
sys.modules.setdefault("keyring", keyring_stub)

from snow_cli.client import ScriptTokenError, ServiceNowClient
from snow_cli.config import Config


def _make_config(tmp_dir, instance="dev.example.com", user="admin", password="pass"):
    return Config(
        instance=instance,
        user=user,
        password=password,
        cookie_file=Path(tmp_dir) / "cookies.txt",
        tmp_dir=Path(tmp_dir),
    )


class RestSessionTests(unittest.TestCase):
    def test_rest_session_has_basic_auth_pre_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
        self.assertEqual(client._rest.auth, ("admin", "pass"))

    def test_rest_session_has_accept_json_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
        self.assertEqual(client._rest.headers.get("Accept"), "application/json")

    def test_scraping_session_is_none_before_first_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
        self.assertIsNone(client._scraping)

    def test_rest_get_calls_rest_session_with_correct_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
            mock_resp = Mock()
            with patch.object(client._rest, "get", return_value=mock_resp) as mock_get:
                result = client.rest_get("/api/now/table/incident", params={"sysparm_limit": "10"})
        mock_get.assert_called_once_with(
            "https://dev.example.com/api/now/table/incident",
            params={"sysparm_limit": "10"},
            headers={},
        )
        self.assertIs(result, mock_resp)


class ScrapingSessionTests(unittest.TestCase):
    def test_scraping_session_created_on_first_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
            with patch.object(client, "_save_cookies"):
                with patch.object(client, "_get_scraping_session") as mock_init:
                    mock_session = Mock()
                    mock_session.get.return_value = Mock()
                    mock_init.return_value = mock_session
                    client.scraping_get("/login.do")
            mock_init.assert_called_once()

    def test_corrupted_cookie_file_prints_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            cookie_file = Path(tmp) / "cookies.txt"
            cookie_file.write_text("not a valid cookie jar file")
            config = Config(
                instance="dev.example.com",
                user="admin",
                password="pass",
                cookie_file=cookie_file,
            )
            client = ServiceNowClient(config)
            buf = io.StringIO()
            with redirect_stderr(buf):
                client._get_scraping_session()
        self.assertIn("Warning", buf.getvalue())

    def test_missing_cookie_file_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config(
                instance="dev.example.com",
                user="admin",
                password="pass",
                cookie_file=Path(tmp) / "nonexistent.txt",
            )
            client = ServiceNowClient(config)
            client._get_scraping_session()  # must not raise

    def test_none_cookie_file_does_not_raise(self):
        config = Config(instance="dev.example.com", user="admin", password="pass")
        client = ServiceNowClient(config)
        client._get_scraping_session()  # must not raise


class TokenExtractionTests(unittest.TestCase):
    def test_extract_token_returns_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
        token = client._extract_token('value="abc123def"', r'value="([a-zA-Z0-9]+)"')
        self.assertEqual(token, "abc123def")

    def test_extract_token_returns_none_when_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
        self.assertIsNone(client._extract_token("no match here", r'value="([a-zA-Z0-9]+)"'))

    def test_get_script_token_raises_script_token_error_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
            mock_response = Mock()
            mock_response.text = "<html>no token here</html>"
            with patch.object(client, "scraping_get", return_value=mock_response):
                with self.assertRaises(ScriptTokenError):
                    client.get_script_token()

    def test_get_login_token_raises_value_error_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
            mock_response = Mock()
            mock_response.text = "<html>no token here</html>"
            with patch.object(client, "scraping_get", return_value=mock_response):
                with self.assertRaises(ValueError):
                    client.get_login_token()

    def test_get_elevate_token_raises_value_error_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
            mock_response = Mock()
            mock_response.text = "<html>no token here</html>"
            with patch.object(client, "scraping_get", return_value=mock_response):
                with self.assertRaises(ValueError):
                    client.get_elevate_token()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
python -m pytest tests/test_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'snow_cli.client'`

- [ ] **Step 3: Create `snow_cli/client.py`**

```python
"""Single HTTP entry point for all ServiceNow communication."""
import http.cookiejar
import re
import sys
from typing import Optional

import requests

from .config import Config


class ScriptTokenError(ValueError):
    """Raised when the background-script execution token cannot be obtained."""


class ServiceNowClient:
    """Facade owning both HTTP transports (cookie-auth scraping + basic-auth REST)."""

    def __init__(self, config: Config):
        self._base_url = f"https://{config.instance}"
        self._cookie_file = config.cookie_file

        self._rest = requests.Session()
        self._rest.auth = (config.user, config.password)
        self._rest.headers.update({"Accept": "application/json"})

        self._scraping: Optional[requests.Session] = None

    # ── REST transport ─────────────────────────────────────────────────────

    def rest_get(self, path: str, params=None, extra_headers=None) -> requests.Response:
        headers = dict(extra_headers) if extra_headers else {}
        return self._rest.get(f"{self._base_url}{path}", params=params, headers=headers)

    # ── Scraping transport ─────────────────────────────────────────────────

    def scraping_get(self, path: str, **kwargs) -> requests.Response:
        session = self._get_scraping_session()
        response = session.get(f"{self._base_url}{path}", **kwargs)
        self._save_cookies()
        return response

    def scraping_post(self, path: str, **kwargs) -> requests.Response:
        session = self._get_scraping_session()
        response = session.post(f"{self._base_url}{path}", **kwargs)
        self._save_cookies()
        return response

    def get_login_token(self) -> str:
        response = self.scraping_get("/login.do")
        token = self._extract_token(
            response.text, r'sysparm_ck[^>]*value="([a-zA-Z0-9_]+)"'
        )
        if not token:
            raise ValueError(f"Could not obtain login token from {self._base_url}")
        return token

    def get_script_token(self) -> str:
        response = self.scraping_get("/sys.scripts.do")
        token = self._extract_token(
            response.text, r'sysparm_ck[^>]*value="([a-zA-Z0-9_]+)"'
        )
        if not token:
            raise ScriptTokenError(
                f"Cannot get security token for {self._base_url}. "
                "Try logging in again (snow login)"
            )
        return token

    def get_elevate_token(self) -> str:
        response = self.scraping_get("/navpage.do")
        token = self._extract_token(response.text, r"g_ck = '([a-zA-Z0-9_]+)'")
        if not token:
            raise ValueError(
                "Could not obtain authentication token to elevate privileges"
            )
        return token

    # ── Private ────────────────────────────────────────────────────────────

    def _get_scraping_session(self) -> requests.Session:
        if self._scraping is None:
            self._scraping = requests.Session()
            self._load_cookies()
        return self._scraping

    def _load_cookies(self):
        if self._cookie_file is None or not self._cookie_file.exists():
            return
        try:
            jar = http.cookiejar.MozillaCookieJar(str(self._cookie_file))
            jar.load(ignore_discard=True, ignore_expires=True)
            for cookie in jar:
                self._scraping.cookies.set_cookie(cookie)
        except Exception as e:
            print(
                f"Warning: cookie file could not be loaded and will be ignored ({e})",
                file=sys.stderr,
            )

    def _save_cookies(self):
        if self._cookie_file is None:
            return
        self._cookie_file.parent.mkdir(parents=True, exist_ok=True)
        jar = http.cookiejar.MozillaCookieJar(str(self._cookie_file))
        for cookie in self._scraping.cookies:
            jar.set_cookie(cookie)
        jar.save(ignore_discard=True, ignore_expires=True)
        self._cookie_file.chmod(0o600)

    def _extract_token(self, html: str, pattern: str) -> Optional[str]:
        match = re.search(pattern, html)
        return match.group(1) if match else None
```

- [ ] **Step 4: Run new tests to confirm they pass**

```bash
python -m pytest tests/test_client.py -v
```

Expected: all tests **PASS**.

- [ ] **Step 5: Run full test suite to confirm nothing broken**

```bash
python -m pytest tests/ -v
```

Expected: all tests **PASS** (`commands.py` still imports from `session.py` — unchanged).

- [ ] **Step 6: Commit**

```bash
git add snow_cli/client.py tests/test_client.py
git commit -m "feat: add ServiceNowClient facade with REST and scraping transports"
```

---

## Task 2: Migrate scraping commands + delete `session.py`

**Files:**
- Modify: `snow_cli/commands.py` (lines 17, 47–84, 87–122, 145, 157, 172–199)
- Delete: `snow_cli/session.py`
- Modify: `tests/test_commands.py` (lines 49, 216, 259, 292, 793–808)

- [ ] **Step 1: Update the import in `commands.py`**

Replace line 17:

```python
# Before
from .session import ScriptTokenError, SnowSession
```

```python
# After
from .client import ScriptTokenError, ServiceNowClient
```

- [ ] **Step 2: Update `login` in `commands.py`**

Replace the body of `login` (lines 47–84). Change `SnowSession(config.instance, config.cookie_file)` to `ServiceNowClient(config)` and replace `session.*` calls with `client.*`:

```python
def login(config: Config) -> int:
    """Login to ServiceNow instance"""
    try:
        config.ensure_credentials_set()

        client = ServiceNowClient(config)
        login_token = client.get_login_token()

        response = client.scraping_post(
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
```

- [ ] **Step 3: Update `elevate` in `commands.py`**

Replace the body of `elevate` (lines 87–122). Change `SnowSession(config.instance, config.cookie_file)` to `ServiceNowClient(config)`:

```python
def elevate(config: Config) -> int:
    """Elevate user privileges (e.g., security_admin role)"""
    try:
        config.ensure_instance_set()

        client = ServiceNowClient(config)
        token = client.get_elevate_token()

        response = client.scraping_post(
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
```

- [ ] **Step 4: Update `run_script` and `_run_script_once` in `commands.py`**

`run_script` creates one `ServiceNowClient(config)` and passes it to both calls of `_run_script_once`. `_run_script_once` signature changes from `(config, script_content)` to `(client, script_content)`.

Replace `run_script` (lines 125–164):

```python
def run_script(
    config: Config,
    script_file: Optional[str] = None,
    script_content: Optional[str] = None,
    auto_login: bool = False,
) -> int:
    """Run a background script on ServiceNow"""
    try:
        config.ensure_instance_set()

        if script_content is None:
            if script_file and script_file != "-":
                with open(script_file, "r") as f:
                    script_content = f.read()
            else:
                script_content = sys.stdin.read()

        client = ServiceNowClient(config)
        try:
            return _run_script_once(client, script_content)
        except ScriptTokenError as exc:
            if not auto_login:
                raise

            print(str(exc), file=sys.stderr)

            if _run_command_with_output_on_stderr(login, config) != 0:
                return 1
            if _run_command_with_output_on_stderr(elevate, config) != 0:
                return 1

            return _run_script_once(client, config, script_content)

    except FileNotFoundError:
        print(f"Script file not found: {script_file}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Script execution error: {e}", file=sys.stderr)
        return 1
```

Replace `_run_script_once` (lines 172–215), changing signature and removing `SnowSession` construction:

```python
def _run_script_once(client: ServiceNowClient, script_content: str) -> int:
    token = client.get_script_token()
    start_marker, end_marker = _generate_output_markers()
    wrapped_script = _wrap_script_with_output_markers(script_content, start_marker, end_marker)

    response = client.scraping_post(
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
            "script": wrapped_script,
        },
    )

    if response.status_code != 200:
        print(f"Script execution failed with status: {response.status_code}", file=sys.stderr)
        return 1

    # Save raw output for debugging
    output_file = config.tmp_dir / "last_run_output.txt"
```

Wait — `_run_script_once` currently uses `config.tmp_dir` after the HTTP call to save debug output. With the new signature `(client, script_content)`, `config` is no longer available. We need to either pass `config` as well, or move the tmp_dir save elsewhere.

Read the rest of `_run_script_once` to see exactly what it does with `config`:

```python
    output_file = config.tmp_dir / "last_run_output.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(output_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(response.text)
```

`config.tmp_dir` is only used for saving debug output. The simplest fix: keep `config` as a second parameter (alongside `client`) so the signature becomes `_run_script_once(client, config, script_content)`. `run_script` already has `config` in scope.

Replace `_run_script_once` with:

```python
def _run_script_once(client: ServiceNowClient, config: Config, script_content: str) -> int:
    token = client.get_script_token()
    start_marker, end_marker = _generate_output_markers()
    wrapped_script = _wrap_script_with_output_markers(script_content, start_marker, end_marker)

    response = client.scraping_post(
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
            "script": wrapped_script,
        },
    )

    if response.status_code != 200:
        print(f"Script execution failed with status: {response.status_code}", file=sys.stderr)
        return 1

    # Save raw output for debugging
    output_file = config.tmp_dir / "last_run_output.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(output_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(response.text)

    _parse_and_display_output(response.text, start_marker, end_marker)
    return 0
```

And update `run_script` to call `_run_script_once(client, config, script_content)`:

```python
def run_script(
    config: Config,
    script_file: Optional[str] = None,
    script_content: Optional[str] = None,
    auto_login: bool = False,
) -> int:
    """Run a background script on ServiceNow"""
    try:
        config.ensure_instance_set()

        if script_content is None:
            if script_file and script_file != "-":
                with open(script_file, "r") as f:
                    script_content = f.read()
            else:
                script_content = sys.stdin.read()

        client = ServiceNowClient(config)
        try:
            return _run_script_once(client, config, script_content)
        except ScriptTokenError as exc:
            if not auto_login:
                raise

            print(str(exc), file=sys.stderr)

            if _run_command_with_output_on_stderr(login, config) != 0:
                return 1
            if _run_command_with_output_on_stderr(elevate, config) != 0:
                return 1

            return _run_script_once(client, config, script_content)

    except FileNotFoundError:
        print(f"Script file not found: {script_file}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Script execution error: {e}", file=sys.stderr)
        return 1
```

- [ ] **Step 5: Delete `snow_cli/session.py`**

```bash
rm snow_cli/session.py
```

- [ ] **Step 6: Update `tests/test_commands.py` — import**

Replace line 49:

```python
# Before
from snow_cli.session import ScriptTokenError
```

```python
# After
from snow_cli.client import ScriptTokenError
```

- [ ] **Step 7: Update `tests/test_commands.py` — auto-login tests**

The three auto-login tests (`test_auto_login_retries_token_failure_once`, `test_auto_login_reports_second_token_failure`, `test_auto_login_stops_when_login_fails`) currently patch `snow_cli.commands.SnowSession`. After the refactor, `run_script` constructs ONE `ServiceNowClient(config)` and reuses it for both calls to `_run_script_once`, so we patch `ServiceNowClient` to return a single mock client.

Replace `test_auto_login_retries_token_failure_once` (lines 194–235):

```python
def test_auto_login_retries_token_failure_once(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = Config(
            instance="dev1234.service-now.com",
            cookie_file=Path(tmp_dir) / "cookies.txt",
            tmp_dir=Path(tmp_dir),
        )
        mock_client = Mock()
        token_error = ScriptTokenError(
            "Cannot get security token for dev1234.service-now.com. Try logging in again (snow login)"
        )
        mock_client.get_script_token.side_effect = [token_error, "token-123"]
        mock_client.scraping_post.return_value = types.SimpleNamespace(status_code=200, text="<PRE></PRE>")

        login_mock = Mock(side_effect=lambda cfg: print(f"Successfully logged in to {cfg.instance}") or 0)
        elevate_mock = Mock(side_effect=lambda cfg: print(f"Successfully elevated privileges on {cfg.instance}") or 0)
        parse_mock = Mock()

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        with patch("snow_cli.commands.ServiceNowClient", return_value=mock_client), \
             patch("snow_cli.commands.login", login_mock), \
             patch("snow_cli.commands.elevate", elevate_mock), \
             patch("snow_cli.commands._generate_output_markers", return_value=("START", "END")), \
             patch("snow_cli.commands._parse_and_display_output", parse_mock):
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                exit_code = run_script(config, script_content="gs.print('Hello');", auto_login=True)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout_buffer.getvalue(), "")
        self.assertIn("Cannot get security token for dev1234.service-now.com.", stderr_buffer.getvalue())
        self.assertIn("Successfully logged in to dev1234.service-now.com", stderr_buffer.getvalue())
        self.assertIn("Successfully elevated privileges on dev1234.service-now.com", stderr_buffer.getvalue())
        self.assertEqual(login_mock.call_count, 1)
        self.assertEqual(elevate_mock.call_count, 1)
        self.assertEqual(parse_mock.call_count, 1)
        self.assertEqual(mock_client.scraping_post.call_count, 1)
        self.assertIn('gs.print("START");', mock_client.scraping_post.call_args.kwargs["data"]["script"])
        self.assertIn("gs.print('Hello');", mock_client.scraping_post.call_args.kwargs["data"]["script"])
        self.assertIn('gs.print("END");', mock_client.scraping_post.call_args.kwargs["data"]["script"])
```

Replace `test_auto_login_reports_second_token_failure` (lines 237–272):

```python
def test_auto_login_reports_second_token_failure(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = Config(
            instance="dev1234.service-now.com",
            cookie_file=Path(tmp_dir) / "cookies.txt",
            tmp_dir=Path(tmp_dir),
        )
        token_error = ScriptTokenError(
            "Cannot get security token for dev1234.service-now.com. Try logging in again (snow login)"
        )
        mock_client = Mock()
        mock_client.get_script_token.side_effect = [token_error, token_error]

        login_mock = Mock(side_effect=lambda cfg: print(f"Successfully logged in to {cfg.instance}") or 0)
        elevate_mock = Mock(side_effect=lambda cfg: print(f"Successfully elevated privileges on {cfg.instance}") or 0)
        parse_mock = Mock()

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        with patch("snow_cli.commands.ServiceNowClient", return_value=mock_client), \
             patch("snow_cli.commands.login", login_mock), \
             patch("snow_cli.commands.elevate", elevate_mock), \
             patch("snow_cli.commands._parse_and_display_output", parse_mock):
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                exit_code = run_script(config, script_content="gs.print('Hello');", auto_login=True)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout_buffer.getvalue(), "")
        self.assertEqual(login_mock.call_count, 1)
        self.assertEqual(elevate_mock.call_count, 1)
        self.assertEqual(parse_mock.call_count, 0)
        self.assertIn("Cannot get security token for dev1234.service-now.com.", stderr_buffer.getvalue())
        self.assertIn("Script execution error: Cannot get security token for dev1234.service-now.com.", stderr_buffer.getvalue())
```

Replace `test_auto_login_stops_when_login_fails` (lines 274–302):

```python
def test_auto_login_stops_when_login_fails(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = Config(
            instance="dev1234.service-now.com",
            cookie_file=Path(tmp_dir) / "cookies.txt",
            tmp_dir=Path(tmp_dir),
        )
        mock_client = Mock()
        mock_client.get_script_token.side_effect = ScriptTokenError(
            "Cannot get security token for dev1234.service-now.com. Try logging in again (snow login)"
        )

        login_mock = Mock(side_effect=lambda cfg: print("Login failed with status code: 401") or 1)
        elevate_mock = Mock()

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        with patch("snow_cli.commands.ServiceNowClient", return_value=mock_client), \
             patch("snow_cli.commands.login", login_mock), \
             patch("snow_cli.commands.elevate", elevate_mock):
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                exit_code = run_script(config, script_content="gs.print('Hello');", auto_login=True)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout_buffer.getvalue(), "")
        self.assertEqual(login_mock.call_count, 1)
        self.assertEqual(elevate_mock.call_count, 0)
        self.assertIn("Login failed with status code: 401", stderr_buffer.getvalue())
```

- [ ] **Step 8: Update `test_corrupted_cookie_file_prints_warning_to_stderr` in `SilentExceptionTests`**

Replace lines 792–809 in `tests/test_commands.py`:

```python
# Before
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

```python
# After
def test_corrupted_cookie_file_prints_warning_to_stderr(self):
    from snow_cli.client import ServiceNowClient
    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_file = Path(tmp_dir) / "cookies.txt"
        cookie_file.write_text("this is not a mozilla cookie jar file")
        config = Config(
            instance="dev.service-now.com",
            user="admin",
            password="pass",
            cookie_file=cookie_file,
        )
        client = ServiceNowClient(config)
        buf = io.StringIO()
        with redirect_stderr(buf):
            client._get_scraping_session()
        self.assertIn("Warning", buf.getvalue())
```

- [ ] **Step 9: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests **PASS**.

- [ ] **Step 10: Commit**

```bash
git add snow_cli/commands.py tests/test_commands.py
git rm snow_cli/session.py
git commit -m "refactor: migrate scraping commands to ServiceNowClient; delete session.py"
```

---

## Task 3: Migrate REST path

**Files:**
- Modify: `snow_cli/commands.py`
  - `_get_table_hierarchy` (around line 442)
  - `_fetch_records` (around line 361)
  - `_fetch_table_fields` (around line 474)
  - `_fetch_record_count` (around line 596)
  - `_fetch_aggregate_records` (around line 636)
  - `search_records`, `search_records_json`, `count_records`, `count_records_value`, `aggregate_records`, `aggregate_records_json`, `table_fields`, `table_fields_json`
- Modify: `tests/test_commands.py`
  - `FetchAggregateRecordsTests`
  - `AggregateRecordsCliTests`
  - `FetchRecordsPaginationTests`
  - `TableFieldsTests`

- [ ] **Step 1: Update `_get_table_hierarchy` in `commands.py`**

Change signature from `(base, auth, table_name)` to `(client, table_name)` and replace the HTTP call:

```python
def _get_table_hierarchy(client: "ServiceNowClient", table_name: str) -> list:
    """Return list of table names from table_name up to the root (most-specific first)."""
    hierarchy = []
    current = table_name
    visited = set()
    while current and current not in visited:
        visited.add(current)
        hierarchy.append(current)
        resp = client.rest_get(
            "/api/now/table/sys_db_object",
            params={
                "sysparm_query": f"name={current}",
                "sysparm_fields": "super_class.name",
                "sysparm_limit": "1",
                "sysparm_display_value": "false",
            },
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
```

- [ ] **Step 2: Update `_fetch_records` in `commands.py`**

Change signature from `(config, table, ...)` to `(client, table, ...)`. Remove `import requests as _requests`, remove URL/auth/headers construction, replace HTTP call:

```python
def _fetch_records(
    client: "ServiceNowClient",
    table: str,
    query: Optional[str] = None,
    order_by: Optional[list] = None,
    order_by_desc: Optional[list] = None,
    fields: Optional[str] = None,
    limit: Optional[int] = None,
    display_values: str = "both",
) -> list:
    """Fetch records from Table API and return as a list of dicts. Raises on error.

    Automatically paginates using sysparm_offset so that all matching records are
    returned regardless of the server-side row cap. Uses the Link response header
    (rel=next) as the authoritative signal for more pages. This handles cases where
    ACL post-filtering causes fewer records than requested to be returned per page.
    Falls back to the page-size heuristic when the header is absent.

    When *limit* is set, at most that many records are returned.
    """
    if limit is not None and limit <= 0:
        return []

    query_parts = []
    if query:
        query_parts.append(query)
    if order_by:
        query_parts.extend([f"ORDERBY{field}" for field in order_by if field])
    if order_by_desc:
        query_parts.extend([f"ORDERBYDESC{field}" for field in order_by_desc if field])

    base_params = {
        "sysparm_display_value": DISPLAY_VALUE_MAP[display_values],
        "sysparm_query": "^".join(query_parts),
    }
    if fields:
        base_params["sysparm_fields"] = fields

    all_records: list = []
    offset = 0

    while True:
        remaining = limit - len(all_records) if limit is not None else None
        page_size = min(_DEFAULT_PAGE_SIZE, remaining) if remaining is not None else _DEFAULT_PAGE_SIZE

        params = {**base_params, "sysparm_limit": str(page_size), "sysparm_offset": str(offset)}
        response = client.rest_get(f"/api/now/table/{table}", params=params)

        if response.status_code != 200:
            raise RuntimeError(
                f"Record query failed with status code: {response.status_code}\n{response.text}"
            )

        payload = response.json()
        page = payload.get("result", [])
        if isinstance(page, dict):
            page = [page]

        all_records.extend(page)

        if limit is not None and len(all_records) >= limit:
            break

        if _has_next_page(response):
            offset += page_size
        elif len(page) < page_size:
            break
        else:
            offset += page_size

    return all_records
```

- [ ] **Step 3: Update `_fetch_table_fields` in `commands.py`**

Change signature from `(config, table_name)` to `(client, table_name)`. Remove `import requests as _requests`, `auth`, `base`. Update calls to `_get_table_hierarchy` and the dictionary fetch:

```python
def _fetch_table_fields(client: "ServiceNowClient", table_name: str) -> list:
    """Return all fields (including inherited) for a table. Raises on error.

    Each entry: {field, label, type, references, defined_on}
    """
    hierarchy = _get_table_hierarchy(client, table_name)
    if not hierarchy:
        raise RuntimeError(f"Table '{table_name}' not found or not accessible.")

    table_in_query = ",".join(hierarchy)
    resp = client.rest_get(
        "/api/now/table/sys_dictionary",
        params={
            "sysparm_query": f"nameIN{table_in_query}^elementISNOTEMPTY",
            "sysparm_fields": "element,column_label,internal_type,reference,name",
            "sysparm_limit": "10000",
            "sysparm_display_value": "all",
            "sysparm_no_count": "true",
        },
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

    table_priority = {t: i for i, t in enumerate(hierarchy)}

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

    seen = {}
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
        key=lambda r: r["field"],
    )
    return result
```

- [ ] **Step 4: Update `_fetch_record_count` in `commands.py`**

Change signature from `(config, table, query)` to `(client, table, query)`. Remove `import requests as _requests`. Replace HTTP call:

```python
def _fetch_record_count(client: "ServiceNowClient", table: str, query: Optional[str] = None) -> int:
    """Call the Aggregate API and return the record count. Raises on error."""
    params = {"sysparm_count": "true"}
    if query:
        params["sysparm_query"] = query
    response = client.rest_get(f"/api/now/stats/{table}", params=params)
    if response.status_code != 200:
        raise RuntimeError(
            f"Record count failed with status code: {response.status_code}\n{response.text}"
        )
    return int(response.json()["result"]["stats"]["count"])
```

- [ ] **Step 5: Update `_fetch_aggregate_records` in `commands.py`**

Change signature from `(config, table, ...)` to `(client, table, ...)`. Remove `import requests as _requests`. Replace HTTP call:

```python
def _fetch_aggregate_records(
    client: "ServiceNowClient",
    table: str,
    query: Optional[str] = None,
    group_by: Optional[List[str]] = None,
    count: bool = False,
    avg: Optional[List[str]] = None,
    sum_fields: Optional[List[str]] = None,
    min_fields: Optional[List[str]] = None,
    max_fields: Optional[List[str]] = None,
    having: Optional[str] = None,
    display_values: str = "both",
) -> List[dict]:
    """Call the Aggregate API and return flattened result rows. Raises on error."""
    params: dict = {
        "sysparm_display_value": DISPLAY_VALUE_MAP[display_values],
    }
    if query:
        params["sysparm_query"] = query
    if group_by:
        params["sysparm_group_by"] = ",".join(group_by)
    if count:
        params["sysparm_count"] = "true"
    if avg:
        params["sysparm_avg"] = ",".join(avg)
    if sum_fields:
        params["sysparm_sum"] = ",".join(sum_fields)
    if min_fields:
        params["sysparm_min"] = ",".join(min_fields)
    if max_fields:
        params["sysparm_max"] = ",".join(max_fields)
    if having:
        params["sysparm_having"] = having

    response = client.rest_get(f"/api/now/stats/{table}", params=params)
    if response.status_code != 200:
        raise RuntimeError(
            f"Aggregate query failed with status code: {response.status_code}\n{response.text}"
        )

    payload = response.json()
    raw_results = payload.get("result", [])
    if isinstance(raw_results, dict):
        raw_results = [raw_results]

    rows = []
    for item in raw_results:
        row: dict = {}
        for gf in item.get("groupby_fields", []):
            field_name = gf.get("field", "")
            display_val = gf.get("display_value", "")
            value_val = gf.get("value", "")
            if display_values == "display":
                row[field_name] = display_val
            elif display_values == "values":
                row[field_name] = value_val
            else:
                row[field_name] = (
                    f"{display_val} ({value_val})" if display_val != value_val else display_val
                )
        for stat_name, stat_val in item.get("stats", {}).items():
            row[stat_name] = stat_val
        rows.append(row)
    return rows
```

- [ ] **Step 6: Update public functions to create `ServiceNowClient(config)` and pass to private helpers**

For each public function, add `client = ServiceNowClient(config)` before the private helper call and change the call signature.

**`search_records`** (around line 819) — change `_fetch_records(config, ...)` to `_fetch_records(client, ...)`:

```python
# Add after config.ensure_credentials_set() and validation, before _fetch_records call:
client = ServiceNowClient(config)
records = _fetch_records(client, table, query, order_by, order_by_desc, fields, limit, display_values)
```

**`search_records_json`** (around line 881):

```python
def search_records_json(config, table, query=None, order_by=None, order_by_desc=None,
                        fields=None, limit=None, display_values="both") -> list:
    config.ensure_credentials_set()
    if display_values not in DISPLAY_VALUE_MAP:
        raise ValueError(f"Invalid display_values '{display_values}'. Use one of: values, display, both.")
    client = ServiceNowClient(config)
    return _fetch_records(client, table, query, order_by, order_by_desc, fields, limit, display_values)
```

**`count_records`** (around line 615):

```python
def count_records(config: Config, table: str, query: Optional[str] = None) -> int:
    try:
        config.ensure_credentials_set()
        client = ServiceNowClient(config)
        count = _fetch_record_count(client, table, query)
        print(count)
        return 0
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Record count error: {e}", file=sys.stderr)
        return 1
```

**`count_records_value`** (around line 630):

```python
def count_records_value(config: Config, table: str, query: Optional[str] = None) -> int:
    config.ensure_credentials_set()
    client = ServiceNowClient(config)
    return _fetch_record_count(client, table, query)
```

**`aggregate_records`** (around line 712) — change `_fetch_aggregate_records(config, ...)` to `_fetch_aggregate_records(client, ...)`:

```python
# Add after config.ensure_credentials_set() and validation, before _fetch_aggregate_records call:
client = ServiceNowClient(config)
records = _fetch_aggregate_records(
    client, table, query=query, group_by=group_by, count=count,
    avg=avg, sum_fields=sum_fields, min_fields=min_fields,
    max_fields=max_fields, having=having, display_values=display_values,
)
```

**`aggregate_records_json`** (around line 787): apply the same pattern — add `client = ServiceNowClient(config)` and change `_fetch_aggregate_records(config, ...)` → `_fetch_aggregate_records(client, ...)`.

**`table_fields`** (around line 557):

```python
# Add after config.ensure_credentials_set() and validation, before _fetch_table_fields call:
client = ServiceNowClient(config)
fields_data = _fetch_table_fields(client, table_name)
```

**`table_fields_json`** (around line 590):

```python
def table_fields_json(config: Config, table_name: str) -> list:
    config.ensure_credentials_set()
    client = ServiceNowClient(config)
    return _fetch_table_fields(client, table_name)
```

- [ ] **Step 7: Update `FetchAggregateRecordsTests` in `tests/test_commands.py`**

These tests call `_fetch_aggregate_records(config, ...)` with `patch("requests.get", ...)`. After the refactor, `_fetch_aggregate_records(client, ...)` takes a `ServiceNowClient`. Replace the config-based approach with a mock client.

Replace `test_count_only_no_groupby_returns_single_row`:

```python
def test_count_only_no_groupby_returns_single_row(self):
    from snow_cli.commands import _fetch_aggregate_records

    payload = {"result": {"stats": {"count": "42"}}}
    mock_client = Mock()
    mock_client.rest_get.return_value = self._mock_response(payload)
    rows = _fetch_aggregate_records(mock_client, "incident", count=True)
    self.assertEqual(rows, [{"count": "42"}])
```

Replace `test_groupby_results_are_flattened`:

```python
def test_groupby_results_are_flattened(self):
    from snow_cli.commands import _fetch_aggregate_records

    payload = {
        "result": [
            {
                "groupby_fields": [
                    {"field": "priority", "value": "1", "display_value": "1 - Critical"}
                ],
                "stats": {"count": "5"},
            },
            {
                "groupby_fields": [
                    {"field": "priority", "value": "2", "display_value": "2 - High"}
                ],
                "stats": {"count": "12"},
            },
        ]
    }
    mock_client = Mock()
    mock_client.rest_get.return_value = self._mock_response(payload)
    rows = _fetch_aggregate_records(mock_client, "incident", count=True, group_by=["priority"])
    self.assertEqual(len(rows), 2)
    self.assertIn("priority", rows[0])
    self.assertIn("count", rows[0])
    self.assertEqual(rows[0]["priority"], "1 - Critical (1)")
    self.assertEqual(rows[0]["count"], "5")
```

Replace `test_http_error_raises_runtime_error`:

```python
def test_http_error_raises_runtime_error(self):
    from snow_cli.commands import _fetch_aggregate_records

    mock_client = Mock()
    mock_client.rest_get.return_value = self._mock_response({}, status=403)
    with self.assertRaises(RuntimeError) as ctx:
        _fetch_aggregate_records(mock_client, "incident", count=True)
    self.assertIn("403", str(ctx.exception))
```

- [ ] **Step 8: Update `AggregateRecordsCliTests` in `tests/test_commands.py`**

These tests call `aggregate_records(config, ...)` (the public function) with `patch("requests.get", ...)`. After the refactor, the public function creates `ServiceNowClient(config)` internally and calls `_fetch_aggregate_records(client, ...)`. Patch `snow_cli.commands.ServiceNowClient` to return a mock client.

Replace `test_count_with_groupby_prints_table`:

```python
def test_count_with_groupby_prints_table(self):
    from snow_cli.commands import aggregate_records

    payload = {
        "result": [
            {
                "groupby_fields": [{"field": "state", "value": "1", "display_value": "New"}],
                "stats": {"count": "7"},
            }
        ]
    }
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload

    mock_client = Mock()
    mock_client.rest_get.return_value = mock_resp

    with tempfile.TemporaryDirectory() as tmp_dir:
        config = self._make_config(tmp_dir)
        out = io.StringIO()
        with patch("snow_cli.commands.ServiceNowClient", return_value=mock_client):
            with redirect_stdout(out):
                code = aggregate_records(
                    config, "incident", count=True, group_by=["state"], fmt="json"
                )
    self.assertEqual(code, 0)
    import json as _json
    data = _json.loads(out.getvalue())
    self.assertEqual(len(data), 1)
    self.assertIn("state", data[0])
    self.assertIn("count", data[0])
    self.assertEqual(data[0]["count"], "7")
```

Replace `test_json_format_outputs_valid_json`:

```python
def test_json_format_outputs_valid_json(self):
    from snow_cli.commands import aggregate_records
    import json as _json

    payload = {"result": {"stats": {"count": "99"}}}
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload

    mock_client = Mock()
    mock_client.rest_get.return_value = mock_resp

    with tempfile.TemporaryDirectory() as tmp_dir:
        config = self._make_config(tmp_dir)
        out = io.StringIO()
        with patch("snow_cli.commands.ServiceNowClient", return_value=mock_client):
            with redirect_stdout(out):
                code = aggregate_records(config, "incident", count=True, fmt="json")
    self.assertEqual(code, 0)
    data = _json.loads(out.getvalue())
    self.assertIsInstance(data, list)
    self.assertEqual(data[0]["count"], "99")
```

- [ ] **Step 9: Update `FetchRecordsPaginationTests` in `tests/test_commands.py`**

These tests call `_fetch_records(config, ...)` with `patch("requests.get", ...)`. After the refactor, `_fetch_records(client, ...)` takes a `ServiceNowClient`. Replace `_make_config` + `patch("requests.get")` with a mock client.

Replace `_mock_get` helper and `_make_config` with `_make_mock_client`:

```python
def _make_mock_client(self, pages, link_next_on_pages=None):
    """Return a mock ServiceNowClient whose rest_get returns successive page responses."""
    link_next_on_pages = set(link_next_on_pages or [])
    responses = []
    for idx, page_records in enumerate(pages):
        mock = Mock()
        mock.status_code = 200
        mock.json.return_value = {"result": page_records}
        if idx in link_next_on_pages:
            mock.headers.get.return_value = '<...>;rel="next"'
        else:
            mock.headers.get.return_value = ""
        responses.append(mock)
    client = Mock()
    client.rest_get.side_effect = responses
    return client
```

Replace `test_single_page_no_pagination_needed`:

```python
def test_single_page_no_pagination_needed(self):
    from snow_cli.commands import _fetch_records

    records = [{"sys_id": {"value": str(i), "display_value": str(i)}} for i in range(10)]
    client = self._make_mock_client([records])
    result = _fetch_records(client, "incident")
    self.assertEqual(len(result), 10)
    self.assertEqual(client.rest_get.call_count, 1)
```

Replace `test_two_pages_are_combined`:

```python
def test_two_pages_are_combined(self):
    from snow_cli.commands import _fetch_records, _DEFAULT_PAGE_SIZE

    page1 = [{"sys_id": {"value": str(i)}} for i in range(_DEFAULT_PAGE_SIZE)]
    page2 = [{"sys_id": {"value": str(i)}} for i in range(5)]
    client = self._make_mock_client([page1, page2])
    result = _fetch_records(client, "incident")
    self.assertEqual(len(result), _DEFAULT_PAGE_SIZE + 5)
    self.assertEqual(client.rest_get.call_count, 2)
```

Replace `test_limit_within_first_page`:

```python
def test_limit_within_first_page(self):
    from snow_cli.commands import _fetch_records

    page1 = [{"sys_id": {"value": str(i)}} for i in range(50)]
    client = self._make_mock_client([page1])
    result = _fetch_records(client, "incident", limit=50)
    self.assertEqual(len(result), 50)
    self.assertEqual(client.rest_get.call_count, 1)
```

Replace `test_zero_limit_returns_empty_without_request`:

```python
def test_zero_limit_returns_empty_without_request(self):
    from snow_cli.commands import _fetch_records

    client = Mock()
    result = _fetch_records(client, "incident", limit=0)
    self.assertEqual(result, [])
    client.rest_get.assert_not_called()
```

For the remaining pagination tests (`test_limit_spanning_two_pages` and any others), apply the same pattern: replace `with tempfile.TemporaryDirectory() as tmp_dir: config = self._make_config(tmp_dir)` and `with patch("requests.get", ...) as mock_get:` with `client = self._make_mock_client(...)`, and replace `mock_get.call_count` with `client.rest_get.call_count`.

Replace `test_limit_spanning_two_pages`:

```python
def test_limit_spanning_two_pages(self):
    from snow_cli.commands import _fetch_records, _DEFAULT_PAGE_SIZE

    limit = _DEFAULT_PAGE_SIZE + 200
    page1 = [{"sys_id": {"value": str(i)}} for i in range(_DEFAULT_PAGE_SIZE)]
    page2 = [{"sys_id": {"value": str(i)}} for i in range(200)]
    client = self._make_mock_client([page1, page2])
    result = _fetch_records(client, "incident", limit=limit)
    self.assertEqual(len(result), limit)
    self.assertEqual(client.rest_get.call_count, 2)
```

Replace `test_empty_table_returns_empty_list`:

```python
def test_empty_table_returns_empty_list(self):
    from snow_cli.commands import _fetch_records

    client = self._make_mock_client([[]])
    result = _fetch_records(client, "incident")
    self.assertEqual(result, [])
    self.assertEqual(client.rest_get.call_count, 1)
```

Replace `test_http_error_raises_runtime_error`:

```python
def test_http_error_raises_runtime_error(self):
    from snow_cli.commands import _fetch_records

    mock_resp = Mock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    client = Mock()
    client.rest_get.return_value = mock_resp
    with self.assertRaises(RuntimeError) as ctx:
        _fetch_records(client, "incident")
    self.assertIn("403", str(ctx.exception))
```

Replace `test_offset_increments_correctly`:

```python
def test_offset_increments_correctly(self):
    from snow_cli.commands import _fetch_records, _DEFAULT_PAGE_SIZE

    page1 = [{"sys_id": {"value": str(i)}} for i in range(_DEFAULT_PAGE_SIZE)]
    page2 = [{"sys_id": {"value": str(i)}} for i in range(3)]
    client = self._make_mock_client([page1, page2])
    _fetch_records(client, "incident")
    first_call_params = client.rest_get.call_args_list[0].kwargs["params"]
    second_call_params = client.rest_get.call_args_list[1].kwargs["params"]
    self.assertEqual(first_call_params["sysparm_offset"], "0")
    self.assertEqual(second_call_params["sysparm_offset"], str(_DEFAULT_PAGE_SIZE))
```

Replace `test_link_next_header_overrides_size_heuristic`:

```python
def test_link_next_header_overrides_size_heuristic(self):
    from snow_cli.commands import _fetch_records, _DEFAULT_PAGE_SIZE

    page1 = [{"sys_id": {"value": str(i)}} for i in range(996)]
    page2 = [{"sys_id": {"value": str(i)}} for i in range(200)]
    client = self._make_mock_client([page1, page2], link_next_on_pages={0})
    result = _fetch_records(client, "incident")
    self.assertEqual(len(result), 996 + 200)
    self.assertEqual(client.rest_get.call_count, 2)
```

Also delete `_make_config` and `_mock_get` from `FetchRecordsPaginationTests` since they are replaced by `_make_mock_client`.

- [ ] **Step 10: Update `TableFieldsTests` in `tests/test_commands.py`**

These tests call `_fetch_table_fields(config, ...)` with `patch("requests.get", ...)`. After the refactor, `_fetch_table_fields(client, ...)` takes a mock client. Replace `_make_config` with a mock client.

In `TableFieldsTests`, replace `_make_config` with `_make_mock_client`:

```python
def _make_mock_client(self, side_effects):
    """Return a mock ServiceNowClient with rest_get returning the given responses in order."""
    client = Mock()
    client.rest_get.side_effect = side_effects
    return client
```

Replace `test_inherited_field_shows_deepest_ancestor`:

```python
def test_inherited_field_shows_deepest_ancestor(self):
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
    client = self._make_mock_client(side_effects)
    fields = _fetch_table_fields(client, "child_table")
    f = next(x for x in fields if x["field"] == "install_status")
    self.assertEqual(f["defined_on"], "root_table")
```

Replace `test_native_field_shows_own_table`:

```python
def test_native_field_shows_own_table(self):
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
    client = self._make_mock_client(side_effects)
    fields = _fetch_table_fields(client, "child_table")
    f = next(x for x in fields if x["field"] == "u_custom")
    self.assertEqual(f["defined_on"], "child_table")
```

Replace `test_child_label_wins_over_parent`:

```python
def test_child_label_wins_over_parent(self):
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
    client = self._make_mock_client(side_effects)
    fields = _fetch_table_fields(client, "child_table")
    f = next(x for x in fields if x["field"] == "state")
    self.assertEqual(f["label"], "Child Label")
    self.assertEqual(f["defined_on"], "parent_table")
```

Also remove `_make_config` from `TableFieldsTests` (the old `with tempfile.TemporaryDirectory()` pattern is gone).

- [ ] **Step 11: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests **PASS**.

- [ ] **Step 12: Commit**

```bash
git add snow_cli/commands.py tests/test_commands.py
git commit -m "refactor: migrate REST commands to ServiceNowClient; remove local requests imports"
```
