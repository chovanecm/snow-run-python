# Security

## Password Storage

The CLI uses **system keyring** to store passwords securely:

### macOS
- Passwords stored in **Keychain**
- Same security as Safari, Mail, etc.
- Access controlled by macOS security

### Linux
- Uses **Secret Service** (libsecret/gnome-keyring)
- Integrated with desktop environment
- Encrypted storage

### Windows
- Uses **Windows Credential Locker**
- System-managed encryption

## Fallback Mode

If system keyring is unavailable (e.g., headless server), passwords are stored in `~/.snow-run/config.json` with:
- File permissions: 600 (owner read/write only)
- Warning displayed when adding instance

## Config File Structure

### With Keyring (Secure)
```json
{
  "default_instance": "dev1234.service-now.com",
  "instances": {
    "dev1234.service-now.com": {
      "user": "admin",
      "keyring": true
    }
  }
}
```

Password stored separately in system keyring as:
- Service: `snow-cli:dev1234.service-now.com`
- Account: `admin`

### Without Keyring (Fallback)
```json
{
  "default_instance": "dev1234.service-now.com",
  "instances": {
    "dev1234.service-now.com": {
      "user": "admin",
      "keyring": false,
      "password": "plaintext_password"
    }
  }
}
```

## Viewing Storage Method

```bash
snow list
```

Output shows storage method:
```
Configured instances:

  dev1234.service-now.com (default)
    User: admin
    Password: Stored in [keyring]

  test5678.service-now.com
    User: testuser
    Password: Stored in [config file]
```

## Best Practices

✅ **Do:**
- Use system keyring (happens automatically)
- Use separate dev/test instances
- Use accounts with minimal required permissions
- Regularly rotate passwords

❌ **Don't:**
- Use production instances
- Share config files
- Commit config files to version control
- Use admin accounts for routine tasks

## macOS Keychain Access

View stored passwords:
1. Open **Keychain Access** app
2. Search for `snow-cli`
3. Double-click to view/edit

Delete passwords:
```bash
# Via CLI
snow remove dev1234.service-now.com

# Or manually in Keychain Access
```

## Linux Secret Service

View/manage credentials using:
- **Seahorse** (GNOME)
- **KWalletManager** (KDE)
- Or command line: `secret-tool lookup service snow-cli:instance`

## Troubleshooting

### "System keyring not available"

On Linux, install Secret Service backend:
```bash
# Ubuntu/Debian
sudo apt-get install gnome-keyring python3-secretstorage

# Fedora
sudo dnf install gnome-keyring python3-secretstorage
```

On headless servers, keyring may not be available. The CLI will fall back to config file storage automatically.

### Migrating from Config File to Keyring

If you previously stored passwords in config file and now have keyring available:

```bash
# Re-add the instance
snow add dev1234.service-now.com
# Enter same credentials
# Password will now be stored in keyring

# Config file will be updated automatically
```

## Cookie Storage

Session cookies are stored separately in:
```
~/.snow-run/tmp/{instance}/cookies.txt
```

These are NOT sensitive like passwords (they expire), but still have file permissions 600.
