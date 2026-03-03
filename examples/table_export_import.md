# Table Export/Import Examples

## Dump Table to File

### Basic dump
```bash
# Dump entire incident table
snow dump incident incidents.json
```

### Dump with query filter
```bash
# Only active incidents
snow dump incident active_incidents.json -q "active=true"

# Incidents from last week
snow dump incident recent_incidents.json -q "sys_created_onRELATIVEGE@dayofweek@ago@1"

# High priority incidents
snow dump incident high_priority.json -q "priority<=2^active=true"
```

### Dump large tables with custom batch size
```bash
# Increase batch size for better performance on large tables
snow dump cmdb_ci_server servers.json --batch-size 5000

# Reduce batch size if experiencing timeouts
snow dump change_request changes.json --batch-size 500
```

## Import Table from File

### Basic import
```bash
# Import records (preserves sys_id, disables business rules)
snow import incident incidents.json
```

### Import with custom batch size
```bash
# Smaller batches for complex tables with many relationships
snow import cmdb_ci_server servers.json --batch-size 50

# Larger batches for simple tables
snow import u_custom_table data.json --batch-size 200
```

## Use Cases

### Backup and Restore
```bash
# Backup a table
snow dump sys_user_group user_groups_backup.json

# Restore from backup (exact restore without business rules)
snow import sys_user_group user_groups_backup.json

# Restore with business rules (useful for triggering validations)
snow import sys_user_group user_groups_backup.json --use-api
```

### Data Migration Between Instances
```bash
# Export from source instance
snow -i dev1234.service-now.com dump incident dev_incidents.json

# Import to target instance (exact clone)
snow -i test5678.service-now.com import incident dev_incidents.json

# Import to target with business rules (triggers notifications, workflows)
snow -i test5678.service-now.com import incident dev_incidents.json --use-api
```

### Selective Data Copy
```bash
# Copy only specific records
snow dump incident vip_incidents.json -q "caller_id.vip=true"
snow -i target.service-now.com import incident vip_incidents.json
```

## Choosing Import Mode

### Use Background Script Mode (default) when:
- Migrating data between instances
- Restoring from backup
- Need exact field values (including system fields)
- Want to avoid triggering workflows/notifications
- Business rules would block the import

### Use API Mode (--use-api) when:
- Need faster import speed
- Want business rules to validate/calculate fields
- Need workflows and notifications to trigger
- Importing into production and want normal processing
- Data should go through standard business logic

## Important Considerations

### Import Behavior

**Background Script Mode (default)**:
- **Business Rules**: Completely bypassed using `setWorkflow(false)`
- **Workflows**: Not triggered during import
- **Notifications**: Not sent
- **System Fields**: Preserved exactly as in source (sys_created_on, sys_updated_on, etc.)
- **sys_id**: Preserved from source file
- **Existing Records**: Updated if sys_id matches
- **Speed**: Slower (background script execution)

**API Mode (--use-api)**:
- **Business Rules**: WILL run normally
- **Workflows**: Will be triggered
- **Notifications**: Will be sent
- **System Fields**: Auto-updated (sys_updated_on, sys_updated_by)
- **sys_id**: Preserved from source file
- **Existing Records**: Updated if sys_id matches
- **Speed**: Much faster (direct API calls)
- **Validation**: Business rule validations will be enforced

### Best Practices
1. **Always test on non-production first**
2. **Back up target table before importing**
3. **Verify data after import**
4. **Use appropriate batch sizes**:
   - Smaller batches (50-100) for complex tables
   - Larger batches (1000-5000) for simple tables
5. **Consider related records**: You may need to export/import multiple tables to preserve relationships

### Performance Tips
- Use larger batch sizes for export (1000-5000 records)
- Use smaller batch sizes for import (50-200 records) to avoid script timeouts
- Filter data with queries to reduce dataset size
- Import during low-usage periods

### Recovery from Failed Import
If an import fails partway through:
1. Check the error messages for specific sys_id failures
2. Records processed before the error are already imported
3. You can re-run the import - it will update existing records
4. Consider splitting the JSON file and importing in smaller chunks

## Quick Comparison Table

| Feature | Background Script Mode (default) | API Mode (--use-api) |
|---------|----------------------------------|----------------------|
| Command | `snow import table file.json` | `snow import table file.json --use-api` |
| Speed | Slower | Much faster |
| Business Rules | Disabled | Run normally |
| Workflows | Disabled | Run normally |
| Notifications | Not sent | Sent normally |
| System Fields | Preserved as-is | Auto-updated |
| Field Validations | Bypassed | Enforced |
| Best For | Migrations, exact clones | Bulk updates with logic |
| Risk Level | Lower (predictable) | Higher (business logic may fail) |

## Real-World Examples

### Example 1: Clone Development Data to Test
```bash
# Export from dev
snow -i dev1234.service-now.com dump incident dev_incidents.json -q "sys_created_onONToday@javascript:gs.beginningOfToday()@javascript:gs.endOfToday()"

# Import to test (exact clone, no business rules)
snow -i test5678.service-now.com import incident dev_incidents.json
```

### Example 2: Bulk Update with Business Logic
```bash
# Export records to update
snow dump incident to_update.json -q "state=2"

# Modify the JSON file (e.g., change state, add notes)
# ... edit the file ...

# Import back with business rules (triggers notifications)
snow import incident to_update.json --use-api
```

### Example 3: Recovery After Accidental Deletion
```bash
# You have a backup from yesterday
# Restore deleted records exactly as they were
snow import incident backup_2026-01-15.json
```
