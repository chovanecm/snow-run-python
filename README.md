# ServiceNow Python CLI

Platform-independent ServiceNow command-line interface written in Python.

## Features

- **Cross-platform**: Works on macOS, Linux, and Windows
- **Better debugging**: Clear error messages and logging
- **No shell dependencies**: No need for GNU tools or bash-specific features
- **Easy to maintain**: Python code is easier to debug than complex shell scripts

## Installation

```bash
cd python-cli
pip install -e .
```

## Configuration

Set environment variables:

```bash
export snow_instance=dev1234.service-now.com
export snow_user=admin
export snow_pwd=your-password
```

Or use command-line options:

```bash
snow --instance dev1234.service-now.com --user admin --password your-password login
```

## Commands

### Login

```bash
snow login
```

Creates a session and stores cookies in `~/.snow-run/tmp/{instance}/cookies.txt`

### Elevate Privileges

```bash
snow elevate
```

Elevates to security_admin role (required for running background scripts on some instances).

### Run Background Script

```bash
# Run a script from file
snow run example.js

# Run from stdin
echo "gs.print('Hello');" | snow run

# Or
snow run < script.js
```

## Debugging

When things go wrong, check:

1. **Last raw output**: `~/.snow-run/tmp/{instance}/last_run_output.txt`
2. **Verbose mode** (coming soon): Add `--debug` flag for detailed HTTP logging
3. **Error messages**: Python provides clear stack traces

## Advantages over Bash version

1. **Platform-independent**: No GNU grep/sed dependencies
2. **Better error handling**: Python exceptions vs shell error codes
3. **Easier to debug**: Can add logging, breakpoints, unit tests
4. **Type hints**: Better IDE support and code documentation
5. **Extensible**: Easy to add new commands and features

## Development

```bash
# Install in development mode
pip install -e .

# Run tests (coming soon)
pytest

# Add logging for debugging
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Migration from Bash

The Python version is designed as a drop-in replacement:

- Same command names: `snow login`, `snow elevate`, `snow run`
- Same environment variables: `snow_instance`, `snow_user`, `snow_pwd`
- Same cookie storage location: `~/.snow-run/tmp/{instance}/cookies.txt`
- Compatible with existing scripts

## TODO

- [ ] Add remaining commands (eval, inspect, table, record, etc.)
- [ ] Add `--debug` flag for verbose HTTP logging
- [ ] Add unit tests
- [ ] Improve output parsing for edge cases
- [ ] Add retry logic for network errors
- [ ] Support for custom SSL certificates
