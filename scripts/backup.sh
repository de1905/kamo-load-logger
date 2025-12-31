#!/bin/bash
# KAMO Load Logger - Database Backup Script
# Creates timestamped backups with rotation

set -e

# Configuration
DATA_DIR="${DATA_DIR:-/app/data}"
BACKUP_DIR="${BACKUP_DIR:-$DATA_DIR/backups}"
DB_FILE="$DATA_DIR/kamo_load.db"
KEEP_DAILY=7
KEEP_WEEKLY=4

# Timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DAY_OF_WEEK=$(date +%u)  # 1=Monday, 7=Sunday

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Check if database exists
if [ ! -f "$DB_FILE" ]; then
    echo "Error: Database file not found at $DB_FILE"
    exit 1
fi

# Create backup filename
if [ "$DAY_OF_WEEK" = "7" ]; then
    # Sunday = weekly backup
    BACKUP_FILE="$BACKUP_DIR/kamo_load_weekly_$TIMESTAMP.db"
    BACKUP_TYPE="weekly"
else
    # Daily backup
    BACKUP_FILE="$BACKUP_DIR/kamo_load_daily_$TIMESTAMP.db"
    BACKUP_TYPE="daily"
fi

echo "Creating $BACKUP_TYPE backup..."
echo "Source: $DB_FILE"
echo "Destination: $BACKUP_FILE"

# Use SQLite's backup command for consistency
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"

# Verify backup
if [ -f "$BACKUP_FILE" ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "Backup created successfully: $SIZE"
else
    echo "Error: Backup file was not created"
    exit 1
fi

# Rotate old backups
echo "Rotating old backups..."

# Remove old daily backups (keep last N)
ls -t "$BACKUP_DIR"/kamo_load_daily_*.db 2>/dev/null | tail -n +$((KEEP_DAILY + 1)) | xargs -r rm -f
DAILY_COUNT=$(ls "$BACKUP_DIR"/kamo_load_daily_*.db 2>/dev/null | wc -l)
echo "Daily backups: $DAILY_COUNT (keeping $KEEP_DAILY)"

# Remove old weekly backups (keep last N)
ls -t "$BACKUP_DIR"/kamo_load_weekly_*.db 2>/dev/null | tail -n +$((KEEP_WEEKLY + 1)) | xargs -r rm -f
WEEKLY_COUNT=$(ls "$BACKUP_DIR"/kamo_load_weekly_*.db 2>/dev/null | wc -l)
echo "Weekly backups: $WEEKLY_COUNT (keeping $KEEP_WEEKLY)"

# Optional: Upload to S3
if [ "$1" = "--s3" ] && [ -n "$2" ]; then
    S3_BUCKET="$2"
    echo "Uploading to S3: s3://$S3_BUCKET/..."
    if command -v aws &> /dev/null; then
        aws s3 cp "$BACKUP_FILE" "s3://$S3_BUCKET/kamo-load-logger/$(basename $BACKUP_FILE)"
        echo "S3 upload complete"
    else
        echo "Warning: AWS CLI not installed, skipping S3 upload"
    fi
fi

echo "Backup completed successfully!"
