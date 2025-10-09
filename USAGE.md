# Usage Guide

## Managing Multiple Instances

The Python CLI stores credentials in `~/.snow-run/config.json` (chmod 600 for security).

### Add Instances

```bash
# Interactive prompt
snow add

# Or specify instance directly
snow add dev1234.service-now.com

# Set as default
snow add --default dev5678.service-now.com
```

Example:
```
$ snow add dev1234.service-now.com
Username for dev1234.service-now.com: admin
Password for admin@dev1234.service-now.com: ********

✓ Added instance: dev1234.service-now.com
  User: admin
  Set as default instance
```

### List Instances

```bash
snow list
```

Example:
```
Configured instances:

  dev1234.service-now.com (default)
    User: admin

  dev5678.service-now.com
    User: testuser
```

### Switch Between Instances

```bash
# Set default instance
snow use dev5678.service-now.com

# Or use --instance flag for one-off commands
snow --instance dev1234.service-now.com login
snow -i dev5678.service-now.com run script.js
```

### Remove Instance

```bash
snow remove dev1234.service-now.com
```

### Check Configuration

```bash
snow info
```

Example:
```
Current instance: dev1234.service-now.com
  User: admin
  Password: (set)
  Cookie file: /Users/you/.snow-run/tmp/dev1234.service-now.com/cookies.txt

Total instances configured: 2

Run 'snow list' to see all instances.
```

## Working with Instances

### Login to Default Instance

```bash
snow login
```

### Login to Specific Instance

```bash
snow --instance dev5678.service-now.com login
# or
snow -i dev5678.service-now.com login
```

### Run Scripts on Different Instances

```bash
# Default instance
snow run script.js

# Specific instance
snow -i dev5678.service-now.com run script.js
```

### Elevate Privileges

```bash
snow elevate

# Or on specific instance
snow -i dev5678.service-now.com elevate
```

## Configuration File

Config is stored in `~/.snow-run/config.json`:

```json
{
  "default_instance": "dev1234.service-now.com",
  "instances": {
    "dev1234.service-now.com": {
      "user": "admin",
      "password": "secret123"
    },
    "dev5678.service-now.com": {
      "user": "testuser",
      "password": "test456"
    }
  }
}
```

File permissions are automatically set to 600 (owner read/write only).

## Security

✓ **Credentials stored locally** in `~/.snow-run/config.json`
✓ **File permissions** automatically set to 600 (owner only)
✓ **Per-instance credentials** - separate credentials for each instance
✓ **No shell config pollution** - nothing added to .bashrc/.zshrc

⚠️ **Still store passwords in plain text** - use only with dev/test instances, not production

## Environment Variables (Optional)

You can still use environment variables to override config:

```bash
export snow_instance=dev1234.service-now.com
export snow_user=admin
export snow_pwd=secret

snow login  # Uses env vars instead of config file
```

Priority order:
1. `--instance` flag
2. Environment variables
3. Config file default instance

## Examples

### Typical Workflow

```bash
# First time setup
snow add dev1234.service-now.com
# Enter username and password

# Login
snow login

# Elevate if needed
snow elevate

# Run scripts
snow run example.js

# Add another instance
snow add test5678.service-now.com

# Switch to it
snow use test5678.service-now.com

# Login to new instance
snow login

# Or use specific instance without switching default
snow -i dev1234.service-now.com run script.js
```

### Working with Multiple Instances Simultaneously

```bash
# Login to both
snow -i dev1234.service-now.com login
snow -i test5678.service-now.com login

# Run scripts on different instances
snow -i dev1234.service-now.com run create_users.js
snow -i test5678.service-now.com run test_users.js
```
