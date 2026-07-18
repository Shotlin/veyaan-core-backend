#!/bin/bash
# VEYAAN Core Backend - Backup Script
# Backs up Neon database to encrypted file in Cloudflare R2

set -euo pipefail

# Configuration
BACKUP_DIR="/tmp/veyaan_backup_$(date +%Y%m%d_%H%M%S)"
R2_BUCKET="${R2_BUCKET:-veyaan-backups}"
ENCRYPTION_KEY_FILE="${ENCRYPTION_KEY_FILE:-/etc/veyaan/backup_encryption_key}"
RCLONE_CONFIG="${RCLONE_CONFIG:-/opt/veyaan/.rclone.conf}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check required environment variables
if [[ -z "${DATABASE_URL:-}" ]]; then
    log_error "DATABASE_URL not set"
    exit 1
fi

if [[ ! -f "$ENCRYPTION_KEY_FILE" ]]; then
    log_error "Encryption key file not found: $ENCRYPTION_KEY_FILE"
    exit 1
fi

if [[ ! -f "$RCLONE_CONFIG" ]]; then
    log_error "Rclone config not found: $RCLONE_CONFIG"
    exit 1
fi

mkdir -p "$BACKUP_DIR"
log_info "Starting backup to $BACKUP_DIR"

# Dump database
log_info "Dumping Neon database..."
pg_dump "$DATABASE_URL" \
    --no-owner \
    --no-privileges \
    --clean \
    --if-exists \
    | gzip > "$BACKUP_DIR/neon_dump.sql.gz"

# Encrypt backup
log_info "Encrypting backup..."
age -r "$(cat "$ENCRYPTION_KEY_FILE")" -e "$BACKUP_DIR/neon_dump.sql.gz" > "$BACKUP_DIR/neon_dump.sql.gz.age"

# Verify encryption
if [[ ! -f "$BACKUP_DIR/neon_dump.sql.gz.age" ]]; then
    log_error "Encryption failed"
    exit 1
fi

# Upload to R2
log_info "Uploading to R2..."
rclone copy "$BACKUP_DIR" "r2:$R2_BUCKET/backups/$(date +%Y/%m/%d)/" \
    --config "$RCLONE_CONFIG" \
    --progress

# Cleanup local backup
log_info "Cleaning up local files..."
rm -rf "$BACKUP_DIR"

# Retention: delete backups older than 30 days
log_info "Applying retention policy (30 days)..."
rclone delete "r2:$R2_BUCKET/backups/" \
    --config "$RCLONE_CONFIG" \
    --min-age 30d \
    --dry-run

log_info "Backup completed successfully!"