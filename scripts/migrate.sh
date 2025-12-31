#!/bin/bash
# KAMO Load Logger - Database Migration Script
# Export/import data between instances

set -e

# Configuration
DATA_DIR="${DATA_DIR:-/app/data}"
DB_FILE="$DATA_DIR/kamo_load.db"

usage() {
    echo "KAMO Load Logger - Database Migration"
    echo ""
    echo "Usage:"
    echo "  $0 export [output_file]    Export data to SQL dump"
    echo "  $0 import <input_file>     Import data from SQL dump"
    echo "  $0 copy <source_db>        Copy data from another database"
    echo ""
    echo "Examples:"
    echo "  $0 export > backup.sql"
    echo "  $0 export data_export.sql"
    echo "  $0 import backup.sql"
    echo "  $0 copy /path/to/old/kamo_load.db"
}

export_data() {
    OUTPUT="${1:-/dev/stdout}"

    if [ ! -f "$DB_FILE" ]; then
        echo "Error: Database not found at $DB_FILE" >&2
        exit 1
    fi

    echo "-- KAMO Load Logger Data Export"
    echo "-- Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "-- Source: $DB_FILE"
    echo ""

    # Export schema and data
    sqlite3 "$DB_FILE" ".dump"

    if [ "$OUTPUT" != "/dev/stdout" ]; then
        echo "Export completed: $OUTPUT" >&2
    fi
}

import_data() {
    INPUT="$1"

    if [ -z "$INPUT" ]; then
        echo "Error: Input file required"
        usage
        exit 1
    fi

    if [ ! -f "$INPUT" ]; then
        echo "Error: Input file not found: $INPUT"
        exit 1
    fi

    echo "KAMO Load Logger - Data Import"
    echo ""
    echo "Input: $INPUT"
    echo "Target: $DB_FILE"
    echo ""

    # Backup current database if exists
    if [ -f "$DB_FILE" ]; then
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        BACKUP="$DATA_DIR/backups/pre_import_$TIMESTAMP.db"
        echo "Backing up current database to: $BACKUP"
        mkdir -p "$DATA_DIR/backups"
        cp "$DB_FILE" "$BACKUP"
    fi

    # Create new database from dump
    echo "Importing data..."
    rm -f "$DB_FILE"
    sqlite3 "$DB_FILE" < "$INPUT"

    # Verify
    LOAD_COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM load_data" 2>/dev/null || echo "0")
    SUB_COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM substation_snapshots" 2>/dev/null || echo "0")

    echo ""
    echo "Import completed!"
    echo "Load records: $LOAD_COUNT"
    echo "Substation records: $SUB_COUNT"
    echo ""
    echo "Restart the container to apply changes."
}

copy_data() {
    SOURCE="$1"

    if [ -z "$SOURCE" ]; then
        echo "Error: Source database required"
        usage
        exit 1
    fi

    if [ ! -f "$SOURCE" ]; then
        echo "Error: Source database not found: $SOURCE"
        exit 1
    fi

    echo "KAMO Load Logger - Database Copy"
    echo ""
    echo "Source: $SOURCE"
    echo "Target: $DB_FILE"
    echo ""

    # Verify source is valid
    if ! sqlite3 "$SOURCE" "SELECT 1" &>/dev/null; then
        echo "Error: Source is not a valid SQLite database"
        exit 1
    fi

    # Get source stats
    SRC_LOAD=$(sqlite3 "$SOURCE" "SELECT COUNT(*) FROM load_data" 2>/dev/null || echo "0")
    SRC_SUB=$(sqlite3 "$SOURCE" "SELECT COUNT(*) FROM substation_snapshots" 2>/dev/null || echo "0")
    echo "Source load records: $SRC_LOAD"
    echo "Source substation records: $SRC_SUB"
    echo ""

    read -p "Copy all data to target? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Copy cancelled"
        exit 0
    fi

    # Backup current database if exists
    if [ -f "$DB_FILE" ]; then
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        BACKUP="$DATA_DIR/backups/pre_copy_$TIMESTAMP.db"
        echo "Backing up current database to: $BACKUP"
        mkdir -p "$DATA_DIR/backups"
        cp "$DB_FILE" "$BACKUP"
    fi

    # Copy database
    echo "Copying database..."
    cp "$SOURCE" "$DB_FILE"

    # Verify
    LOAD_COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM load_data")
    echo ""
    echo "Copy completed!"
    echo "Load records: $LOAD_COUNT"
    echo ""
    echo "Restart the container to apply changes."
}

# Main
case "${1:-}" in
    export)
        export_data "$2"
        ;;
    import)
        import_data "$2"
        ;;
    copy)
        copy_data "$2"
        ;;
    *)
        usage
        exit 1
        ;;
esac
