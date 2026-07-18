# Runbook: Backup and Restore

**Service**: Neon (PostgreSQL) database backup via `infrastructure/scripts/backup.sh`  
**Frequency**: Daily (recommended cron: `0 2 * * *`)  
**Retention**: 30 days (configurable via `RETENTION_DAYS` env var)

---

## Backup Procedure

### Prerequisites

- `age` encryption tool installed on the backup host
- `rclone` configured with Cloudflare R2 credentials at `$RCLONE_CONFIG`
- Age recipient public key stored at `$AGE_RECIPIENT_FILE`
- `pg_dump` available (postgres-client package)
- `DATABASE_URL` environment variable set

### Run a Manual Backup

```bash
# Set required vars
export DATABASE_URL="postgresql://veyaan:password@host:5432/veyaan_prod"
export AGE_RECIPIENT_FILE="/etc/veyaan/age_recipient"
export RCLONE_CONFIG="/opt/veyaan/.rclone.conf"
export R2_BUCKET="veyaan-backups"
export RETENTION_DAYS=30

# Run backup
bash infrastructure/scripts/backup.sh
```

### Verify Backup Succeeded

```bash
# List recent backups in R2
rclone ls "r2:$R2_BUCKET/backups/$(date +%Y/%m/%d)/" --config "$RCLONE_CONFIG"

# Confirm files uploaded
rclone ls "r2:$R2_BUCKET/backups/" --config "$RCLONE_CONFIG" | tail -10
```

### Verify Checksum

```bash
# Download backup and checksum
rclone copy "r2:$R2_BUCKET/backups/YYYY/MM/DD/" /tmp/restore_check/ --config "$RCLONE_CONFIG"

# Verify age file exists and is non-empty
ls -lh /tmp/restore_check/neon_dump.sql.gz.age

# Confirm checksum is recorded
cat /tmp/restore_check/backup_metadata.json
```

---

## Restore Procedure

> [!CAUTION]
> Restore will **replace all data** in the target database. Confirm you are using the correct backup file and target before proceeding.

### Step 1: Download Backup

```bash
export BACKUP_DATE="2026/07/18"  # Set to the backup date
export RESTORE_DIR="/tmp/veyaan_restore"
mkdir -p "$RESTORE_DIR"

rclone copy "r2:${R2_BUCKET}/backups/${BACKUP_DATE}/" "$RESTORE_DIR/" --config "$RCLONE_CONFIG"

# Verify files present
ls -lh "$RESTORE_DIR/"
```

### Step 2: Decrypt

```bash
export AGE_IDENTITY_FILE="/etc/veyaan/age_identity"  # private key

age --decrypt \
    -i "$AGE_IDENTITY_FILE" \
    -o "$RESTORE_DIR/neon_dump.sql.gz" \
    "$RESTORE_DIR/neon_dump.sql.gz.age"
```

### Step 3: Verify Checksum

```bash
# Compare computed checksum against stored checksum
sha256sum "$RESTORE_DIR/neon_dump.sql.gz" > /tmp/computed.sha256
diff /tmp/computed.sha256 "$RESTORE_DIR/neon_dump.sql.gz.sha256"
echo "Checksum OK: $?"
```

### Step 4: Restore to Database

```bash
# Decompress and restore
gunzip -c "$RESTORE_DIR/neon_dump.sql.gz" | psql "$DATABASE_URL"
```

### Step 5: Verify Data Integrity

```sql
-- Verify key table counts
SELECT 'users' AS tbl, count(*) FROM users
UNION ALL SELECT 'devices', count(*) FROM devices
UNION ALL SELECT 'commands', count(*) FROM commands
UNION ALL SELECT 'approvals', count(*) FROM approvals;
```

### Step 6: Run Alembic Migrations

After restore, verify schema is up to date:

```bash
alembic current
alembic upgrade head
```

### Step 7: Restart Services

```bash
docker compose restart api gateway outbox-publisher command-consumer scheduler
```

---

## Scheduled Backup (Cron)

Add to crontab on the Oracle ARM64 host:

```cron
# Daily backup at 2 AM UTC
0 2 * * * /bin/bash /opt/veyaan/infrastructure/scripts/backup.sh >> /var/log/veyaan_backup.log 2>&1
```

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `Age recipient file not found` | Missing `/etc/veyaan/age_recipient` | Create file with age public key |
| `Rclone config not found` | Missing rclone config | Run `rclone config` to set up R2 remote |
| `pg_dump: error connecting` | Wrong `DATABASE_URL` | Verify connection string |
| `Checksum mismatch` | Corrupted backup | Use next most recent backup |
| `age: malformed encrypted file` | Wrong identity key | Verify age private key matches recipient |
