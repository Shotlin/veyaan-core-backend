#!/bin/bash
# VEYAAN Core Backend - Backup Script
# Backs up Neon database to encrypted file in Cloudflare R2

set -euo pipefail

BACKUP_DIR="/tmp/veyaan_backup_$(date +%Y%m%d_%H%M%S)"
R2_BUCKET="${R2_BUCKET:-veyaan-backups}"
AGE_RECIPIENT_FILE="${AGE_RECIPIENT_FILE:-/etc/veyaan/age_recipient}"
RCLONE_CONFIG="${RCLONE_CONFIG:-/opt/veyaan/.rclone.conf}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DRY_RUN="${DRY_RUN:-true}"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

if [[ -z "${DATABASE_URL:-}" ]]; then
    log_error "DATABASE_URL not set"
    exit 1
fi

if [[ ! -f "$AGE_RECIPIENT_FILE" ]]; then
    log_error "Age recipient file not found: $AGE_RECIPIENT_FILE"
    exit 1
fi

if [[ ! -f "$RCLONE_CONFIG" ]]; then
    log_error "Rclone config not found: $RCLONE_CONFIG"
    exit 1
fi

mkdir -p "$BACKUP_DIR"
log_info "Starting backup to $BACKUP_DIR"

log_info "Dumping database..."
pg_dump "$DATABASE_URL" \
    --no-owner \
    --no-privileges \
    --clean \
    --if-exists \
    | gzip > "$BACKUP_DIR/neon_dump.sql.gz"

log_info "Computing checksum..."
sha256sum "$BACKUP_DIR/neon_dump.sql.gz" > "$BACKUP_DIR/neon_dump.sql.gz.sha256"

log_info "Encrypting backup..."
age -r "$(cat "$AGE_RECIPIENT_FILE")" -o "$BACKUP_DIR/neon_dump.sql.gz.age" "$BACKUP_DIR/neon_dump.sql.gz"

if [[ ! -f "$BACKUP_DIR/neon_dump.sql.gz.age" ]]; then
    log_error "Encryption failed"
    exit 1
fi

rm -f "$BACKUP_DIR/neon_dump.sql.gz"

log_info "Recording metadata..."
cat > "$BACKUP_DIR/backup_metadata.json" <<EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "schema_version": "1",
    "application_version": "${APP_VERSION:-unknown}",
    "checksum_algorithm": "sha256"
}
EOF

log_info "Uploading to R2..."
rclone copy "$BACKUP_DIR" "r2:$R2_BUCKET/backups/$(date +%Y/%m/%d)/" \
    --config "$RCLONE_CONFIG" \
    --progress

rm -rf "$BACKUP_DIR"

log_info "Applying retention policy ($RETENTION_DAYS days)..."
if [[ "$DRY_RUN" == "true" ]]; then
    log_info "DRY RUN: would delete backups older than $RETENTION_DAYS days:"
    rclone lsf "r2:$R2_BUCKET/backups/" \
        --config "$RCLONE_CONFIG" \
        --min-age "${RETENTION_DAYS}d" --recursive | while read -r file; do
        log_info "DRY RUN: would delete: $file"
    done
else
    log_info "Deleting backups older than $RETENTION_DAYS days:"
    rclone lsf "r2:$R2_BUCKET/backups/" \
        --config "$RCLONE_CONFIG" \
        --min-age "${RETENTION_DAYS}d" --recursive | while read -r file; do
        log_info "Deleting backup object: $file"
    done
    rclone delete "r2:$R2_BUCKET/backups/" \
        --config "$RCLONE_CONFIG" \
        --min-age "${RETENTION_DAYS}d"
    log_info "Retention cleanup completed"
fi

log_info "Backup completed successfully!"
