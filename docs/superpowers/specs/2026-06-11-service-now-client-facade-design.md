# Design: ServiceNowClient Facade (Finding 2 — Two HTTP Client Patterns)

**Date:** 2026-06-11
**Scope:** `snow_cli/session.py`, `snow_cli/commands.py`, `snow_cli/client.py` (new)
**Principle:** GoF Facade; PP Orthogonality

---

## Problem

Two parallel HTTP paths to ServiceNow coexist in the codebase:

1. **`SnowSession`** (`session.py`) — cookie-based `requests.Session` for UI scraping: login, elevate, run_script. Manages cookie persistence via MozillaCookieJar.
2. **`_requests.get(auth=(user, password))`** — bare basic-auth calls, locally `import`ed inside each of four `_fetch_*` functions in `commands.py`. No shared session, no connection pooling.

Cross-cutting concerns (timeout, SSL verify, proxy, retries) must be applied in two separate places. Every `_fetch_*` function re-imports `requests`, re-constructs auth, and re-specifies headers independently.

---

## Approach: Full Facade — `ServiceNowClient` absorbs `SnowSession`

One new class, `ServiceNowClient`, becomes the single HTTP entry point. `SnowSession` is deleted. Public command function signatures are unchanged.

---

## Files

| File | Action | Change |
|---|---|---|
| `snow_cli/client.py` | **Create** | `ServiceNowClient` class + `ScriptTokenError` |
| `snow_cli/session.py` | **Delete** | Absorbed into `client.py` |
| `snow_cli/commands.py` | **Modify** | Import swap; private helpers take `client`; local `import requests` removed |
| `tests/test_commands.py` | **Modify** | Mock `ServiceNowClient` instead of `SnowSession` |

---

## `ServiceNowClient` design

### `__init__`

```python
def __init__(self, config: Config):
    self._base_url = f"https://{config.instance}"
    self._cookie_file = config.cookie_file

    # REST session — always initialized; basic auth pre-set
    self._rest = requests.Session()
    self._rest.auth = (config.user, config.password)
    self._rest.headers.update({"Accept": "application/json"})

    # Scraping session — lazy; only for login/elevate/run_script
    self._scraping: Optional[requests.Session] = None
```

The scraping session is **lazily initialized** on the first call to `scraping_get()` or `scraping_post()`. REST-only commands (`search_records`, `count_records`, `aggregate_records`, `search_table_fields`) never trigger it, so `cookie_file=None` is safe for those callers.

### Public interface

**Cookie-auth transport** (absorbed from `SnowSession`):
```python
def scraping_get(self, path: str, **kwargs) -> requests.Response
def scraping_post(self, path: str, **kwargs) -> requests.Response
def get_login_token(self) -> str
def get_script_token(self) -> str       # raises ScriptTokenError if token absent
def get_elevate_token(self) -> str
```

**Basic-auth REST transport**:
```python
def rest_get(self, path: str, params=None, extra_headers=None) -> requests.Response
```

**Private**:
```python
def _get_scraping_session(self) -> requests.Session   # lazy init + cookie load
def _load_cookies(self)
def _save_cookies(self)
def _extract_token(self, html: str, pattern: str) -> Optional[str]
```

`ScriptTokenError` is defined at module level in `client.py` (moved from `session.py`).

---

## Data flow

### Before

```
login(config)
  └─ SnowSession(config.instance, config.cookie_file)   # per call
       └─ session.get/post()

search_records(config, ...)
  └─ _fetch_records(config, ...)
       └─ import requests as _requests                  # per function
            └─ _requests.get(url, auth=(user, password))
```

### After

```
login(config)
  └─ ServiceNowClient(config)                           # once per command
       └─ client.get_login_token()  → scraping_get()
       └─ client.scraping_post()

search_records(config, ...)
  └─ ServiceNowClient(config)                           # once per command
       └─ _fetch_records(client, ...)
            └─ client.rest_get()                        # no local import, shared session
```

---

## Changes to `commands.py`

### Public functions — signatures unchanged

`login(config)`, `elevate(config)`, `run_script(config, ...)`, `search_records(config, ...)`, `count_records(config, ...)`, `aggregate_records(config, ...)`, `search_table_fields(config, ...)` all keep their existing signatures.

Each constructs `ServiceNowClient(config)` once internally and passes it to private helpers.

`run_script` is the one function that calls both scraping operations (`_run_script_once`, `login`, `elevate`) — all via the same `client` instance, so the cookie session is initialized once and reused across the auto-login retry flow.

### Private helpers — `config` → `client`

| Function | Before | After |
|---|---|---|
| `_run_script_once` | `(config, script)` | `(client, script)` |
| `_fetch_records` | `(config, table, ...)` | `(client, table, ...)` |
| `_fetch_aggregate_records` | `(config, table, ...)` | `(client, table, ...)` |
| `_fetch_table_fields` | `(config, table)` | `(client, table)` |
| `_fetch_record_count` | `(config, table, ...)` | `(client, table, ...)` |

All local `import requests as _requests` statements inside these functions are removed.

### Import change

```python
# Before
from .session import ScriptTokenError, SnowSession

# After
from .client import ScriptTokenError, ServiceNowClient
```

---

## Error handling

`ScriptTokenError` relocates from `session.py` to `client.py`. Raised by `get_script_token()` when the CSRF token cannot be extracted. Callers in `commands.py` (`run_script`, `_run_script_once`) catch it as before — no behavioral change.

---

## Cross-cutting concerns

Timeout, SSL verify, and proxy configuration are set once in `ServiceNowClient.__init__` and apply to both `_rest` and `_scraping` sessions. Today there is no explicit timeout or proxy config — adding it in one place is the payoff of this refactor.

---

## Testing

`SnowSession` is mocked in current tests. After this change, `ServiceNowClient` is mocked at the same boundary. The mock target moves from `snow_cli.commands.SnowSession` to `snow_cli.commands.ServiceNowClient`. Test intent and structure are unchanged.

New unit tests for `ServiceNowClient` itself cover:
- REST session has basic auth pre-set
- Scraping session is not initialized before first `scraping_get`/`scraping_post` call
- Cookie load/save round-trip
- Token extraction (login, script, elevate)
- `ScriptTokenError` raised when token absent
