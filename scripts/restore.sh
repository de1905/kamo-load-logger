#!/bin/bash
# KAMO Load Logger - Database Restore Script
# Restores from a backup file

set -e

# Configuration
DATA_DIR="${DATA_DIR:-/app/data}"
DB_FILE="$DATA_DIR/kamo_load.db"

# Check arguments
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file>"
    echo ""
    echo "Available backups:"
    ls -lh "$DATA_DIR/backups/"*.db 2>/dev/null || echo "  No backups found"
    exit 1
fi

BACKUP_FILE="$1"

# Check if backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    # Try prepending backup directory
    if [ -f "$DATA_DIR/backups/$BACKUP_FILE" ]; then
        BACKUP_FILE="$DATA_DIR/backups/$BACKUP_FILE"
    else
        echo "Error: Backup file not found: $BACKUP_FILE"
        exit 1
    fi
fi

echo "KAMO Load Logger - Database Restore"
echo "===================================="
echo ""
echo "Backup file: $BACKUP_FILE"
echo "Target: $DB_FILE"
echo ""

# Verify backup file is a valid SQLite database
if ! sqlite3 "$BACKUP_FILE" "SELECT 1" &>/dev/null; then
    echo "Error: Backup file is not a valid SQLite database"
    exit 1
fi

# Get backup info
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
BACKUP_RECORDS=$(sqlite3 "$BACKUP_FILE" "SELECT COUNT(*) FROM load_data" 2>/dev/null || echo "unknown")
echo "Backup size: $BACKUP_SIZE"
echo "Load records: $BACKUP_RECORDS"
echo ""

# Confirm
read -p "This will REPLACE the current database. Continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Restore cancelled"
    exit 0
fi

# Stop the service if running (in Docker context)
echo ""
echo "Restoring database..."

# Create backup of current database (if exists)
if [ -f "$DB_FILE" ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    CURRENT_BACKUP="$DATA_DIR/backups/pre_restore_$TIMESTAMP.db"
    echo "Backing up current database to: $CURRENT_BACKUP"
    cp "$DB_FILE" "$CURRENT_BACKUP"
fi

# Restore
cp "$BACKUP_FILE" "$DB_FILE"

# Verify restore
if sqlite3 "$DB_FILE" "SELECT 1" &>/dev/null; then
    NEW_RECORDS=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM load_data")
    echo ""
    echo "Restore completed successfully!"
    echo "Load records in restored database: $NEW_RECORDS"
    echo ""
    echo "Note: Restart the container to apply changes"
else
    echo "Error: Restore verification failed"
    exit 1
fi
