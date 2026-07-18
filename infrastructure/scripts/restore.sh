#!/bin/bash
# VEYAAN Core Backend - Restore Script

set -euo pipefail

RESTORE_DIR="/tmp/veyaan_restore_$(date +%Y%m%d_%H%M%S)"
AGE_IDENTITY_FILE="${AGE_IDENTITY_FILE:-/etc/veyaan/age_identity}"
RCLONE_CONFIG="${RCLONE_CONFIG:-/opt/veyaan/.rclone.conf}"
BACKUP_PATH="${1:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

cleanup() {
    log_info "Cleaning up temporary files..."
    rm -rf "$RESTORE_DIR"
}
trap cleanup EXIT

if [[ -z "${DATABASE_URL:-}" ]]; then
    log_error "DATABASE_URL not set"
    exit 1
fi

if [[ ! -f "$AGE_IDENTITY_FILE" ]]; then
    log_error "Age identity file not found: $AGE_IDENTITY_FILE"
    exit 1
fi

if [[ -z "$BACKUP_PATH" ]]; then
    log_error "Usage: $0 <r2_backup_path>"
    log_error "Example: $0 r2:veyaan-backups/backups/2025/01/15/"
    exit 1
fi

log_warn "This will OVERWRITE the current database!"
read -p "Are you sure? (type 'RESTORE' to confirm): " confirm
if [[ "$confirm" != "RESTORE" ]]; then
    log_info "Restore cancelled."
    exit 1
fi

mkdir -p "$RESTORE_DIR"
log_info "Starting restore from $BACKUP_PATH"

log_info "Downloading backup..."
rclone copy "$BACKUP_PATH" "$RESTORE_DIR" --config "$RCLONE_CONFIG" --progress

if [[ -f "$RESTORE_DIR/neon_dump.sql.gz.sha256" ]]; then
    log_info "Verifying checksum..."
    (cd "$RESTORE_DIR" && sha256sum -c "neon_dump.sql.gz.sha256")
    log_info "Checksum verified"
fi

if [[ ! -f "$RESTORE_DIR/neon_dump.sql.gz.age" ]]; then
    log_error "Encrypted backup not found"
    exit 1
fi

log_info "Decrypting backup..."
age -d -i "$AGE_IDENTITY_FILE" -o "$RESTORE_DIR/neon_dump.sql.gz" "$RESTORE_DIR/neon_dump.sql.gz.age"

log_info "Restoring database..."
gunzip -c "$RESTORE_DIR/neon_dump.sql.gz" | psql "$DATABASE_URL" -v ON_ERROR_STOP=1

log_info "Verifying Alembic version..."
alembic current

log_info "Database restored successfully!"
log_info "Note: Restart application services to connect to restored database."
