#!/bin/bash
#
# MetaZebrobot Database Backup Script
#
# This script creates daily backups of the SQLite database and
# automatically removes backups older than 7 days.
#
# Backups are stored on the network drive for redundancy:
#   /groups/ahrens/ahrenslab/jeremy/zebrobot/backups/
#
# Setup:
#   1. Make executable: chmod +x deploy/backup_database.sh
#   2. Add to crontab:  crontab -e
#   3. Add this line for nightly backup at 2 AM:
#
#      0 2 * * * /home/delahantyj@hhmi.org/gitrepos/metazebrobot/deploy/backup_database.sh >> /home/delahantyj@hhmi.org/zebrobot_backup.log 2>&1
#
#      Schedule explanation:
#      0 2 * * * = At 2:00 AM every day
#      >> ...log = Append output to log file
#      2>&1      = Include errors in the log
#
# See BACKUP_CRONTAB_GUIDE.md for detailed documentation.
#

# Configuration
DB_PATH="/nvme1/zebrobot.db"
BACKUP_DIR="/groups/ahrens/ahrenslab/jeremy/zebrobot/backups"
DAYS_TO_KEEP=7

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Generate timestamp for backup filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/zebrobot_$TIMESTAMP.db"

# Create the backup
# Using cp with SQLite is safe for read-only backups when no writes are occurring
# For extra safety, we use the SQLite backup command if available
if command -v sqlite3 &> /dev/null; then
    # Use SQLite's built-in backup (safest method)
    sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"
    BACKUP_METHOD="sqlite3 backup"
else
    # Fall back to file copy
    cp "$DB_PATH" "$BACKUP_FILE"
    BACKUP_METHOD="file copy"
fi

# Check if backup was successful
if [ -f "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "$(date): Backup successful - $BACKUP_FILE ($BACKUP_SIZE) via $BACKUP_METHOD"

    # Remove backups older than DAYS_TO_KEEP days
    DELETED_COUNT=$(find "$BACKUP_DIR" -name "zebrobot_*.db" -type f -mtime +$DAYS_TO_KEEP -delete -print | wc -l)
    if [ "$DELETED_COUNT" -gt 0 ]; then
        echo "$(date): Removed $DELETED_COUNT old backup(s)"
    fi
else
    echo "$(date): ERROR - Backup failed!" >&2
    exit 1
fi

# List current backups
echo "$(date): Current backups:"
ls -lh "$BACKUP_DIR"/zebrobot_*.db 2>/dev/null | tail -5
