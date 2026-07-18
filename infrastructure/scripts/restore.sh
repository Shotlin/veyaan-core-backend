#!/bin/bash
# VEYAAN Core Backend - Restore Script
# Restores Neon database from encrypted backup in Cloudflare R2

set -euo pipefail

# Configuration
R2_BUCKET="${R2_BUCKET:-veyaan-backups}"
ENCRYPTION_KEY_FILE="${ENCRYPTION_KEY_FILE:-/etc/veyaan/backup_encryption_key}"
RCLONE_CONFIG="${RCLONE_CONFIG:-/opt/veyaan/.rclone.conf}"
RESTORE_DIR="/tmp/veyaan_restore_$(date +%Y%m%d_%H%M%S)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Usage
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <backup-date>"
    echo "Example: $0 2024/01/15"
    echo ""
    echo "Available backups:"
    rclone lsf "r2:$R2_BUCKET/backups/" --config "$RCLONE_CONFIG"
    exit 1
fi

BACKUP_DATE="$1"

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

# Confirm restore
log_warn "This will REPLACE the current database with backup from $BACKUP_DATE"
read -p "Are you sure? Type 'YES' to confirm: " confirm
if [[ "$confirm" != "YES" ]]; then
    log_info "Restore cancelled"
    exit 0
fi

mkdir -p "$RESTORE_DIR"
log_info "Restoring to $RESTORE_DIR"

# Download backup
log_info "Downloading backup from R2..."
rclone copy "r2:$R2_BUCKET/backups/$BACKUP_DATE/" "$RESTORE_DIR/" \
    --config "$RCLONE_CONFIG" \
    --progress

# Find encrypted backup
BACKUP_FILE=$(find "$RESTORE_DIR" -name "*.age" | head -1)
if [[ -z "$BACKUP_FILE" ]]; then
    log_error "No encrypted backup found in $RESTORE_DIR"
    exit 1
fi

log_info "Found backup: $BACKUP_FILE"

# Decrypt
log_info "Decrypting backup..."
age -d -i "$ENCRYPTION_KEY_FILE" "$BACKUP_FILE" > "$RESTORE_DIR/neon_dump.sql.gz"

# Decompress
log_info "Decompressing..."
gunzip "$RESTORE_DIR/neon_dump.sql.gz"

# Restore database
log_info "Restoring database..."
psql "$DATABASE_URL" -f "$RESTORE_DIR/neon_dump.sql" -v ON_ERROR_STOP=1

# Cleanup
log_info "Cleaning up..."
rm -rf "$RESTORE_DIR"

log_info "Restore completed successfully!"
log_info "Please restart the API and gateway services to reload connections."