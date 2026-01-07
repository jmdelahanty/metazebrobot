# Database Backup Crontab Guide

This guide explains how to set up automated nightly backups of the MetaZebrobot database using cron.

## What is Cron?

**Cron** is a Linux scheduler that runs commands automatically at specified times. You define schedules in a file called your "crontab" (cron table).

## Setting Up the Nightly Backup

### Step 1: Open your crontab
```bash
crontab -e
```

This opens your personal crontab file in a text editor (usually nano or vim).

### Step 2: Add the backup job
Add this line at the bottom of the file:
```
0 2 * * * /home/delahantyj@hhmi.org/gitrepos/metazebrobot/deploy/backup_database.sh >> /home/delahantyj@hhmi.org/zebrobot_backup.log 2>&1
```

### Step 3: Save and exit
- In nano: `Ctrl+O` to save, `Ctrl+X` to exit
- In vim: `:wq` and Enter

---

## Understanding Crontab Syntax

A crontab line has this format:
```
* * * * * command
│ │ │ │ │
│ │ │ │ └── Day of week (0-7, where 0 and 7 are Sunday)
│ │ │ └──── Month (1-12)
│ │ └────── Day of month (1-31)
│ └──────── Hour (0-23)
└────────── Minute (0-59)
```

### Our Backup Schedule Explained

```
0 2 * * *
│ │ │ │ │
│ │ │ │ └── * = Every day of the week
│ │ │ └──── * = Every month
│ │ └────── * = Every day of the month
│ └──────── 2 = At 2 AM (hour 2 in 24-hour format)
└────────── 0 = At minute 0 (top of the hour)
```

**Translation**: "Run at 2:00 AM every day"

### Common Crontab Examples

| Schedule | Crontab | Meaning |
|----------|---------|---------|
| Every day at 2 AM | `0 2 * * *` | Our backup schedule |
| Every day at midnight | `0 0 * * *` | Start of each day |
| Every hour | `0 * * * *` | Top of every hour |
| Every 15 minutes | `*/15 * * * *` | 0, 15, 30, 45 mins |
| Weekdays at 9 AM | `0 9 * * 1-5` | Mon-Fri only |
| Sundays at 3 AM | `0 3 * * 0` | Weekly on Sunday |
| First of month at 1 AM | `0 1 1 * *` | Monthly backup |

---

## Understanding the Full Command

```bash
/home/delahantyj@hhmi.org/gitrepos/metazebrobot/deploy/backup_database.sh >> /home/delahantyj@hhmi.org/zebrobot_backup.log 2>&1
```

| Part | Meaning |
|------|---------|
| `/home/.../backup_database.sh` | The backup script to run |
| `>>` | Append output to file (don't overwrite) |
| `.../zebrobot_backup.log` | Log file for backup output |
| `2>&1` | Also capture error messages in the log |

---

## Managing Your Crontab

| Command | What it does |
|---------|--------------|
| `crontab -e` | Edit your crontab |
| `crontab -l` | List your current crontab |
| `crontab -r` | Remove your entire crontab (careful!) |

---

## What the Backup Script Does

Location: `deploy/backup_database.sh`

1. **Creates a timestamped copy** of the database
   - From: `/nvme1/zebrobot.db`
   - To: `/groups/ahrens/ahrenslab/jeremy/zebrobot/backups/zebrobot_YYYYMMDD_HHMMSS.db`

2. **Auto-deletes old backups** older than 7 days

3. **Logs the result** with timestamp and file size

---

## Checking Your Backups

### View backup files
```bash
ls -lh /groups/ahrens/ahrenslab/jeremy/zebrobot/backups/
```

### View backup log
```bash
cat ~/zebrobot_backup.log
```

### View last few log entries
```bash
tail -20 ~/zebrobot_backup.log
```

---

## Troubleshooting

### Backup not running?

1. **Check crontab is saved**:
   ```bash
   crontab -l
   ```
   You should see your backup line.

2. **Check the log file**:
   ```bash
   cat ~/zebrobot_backup.log
   ```

3. **Test manually**:
   ```bash
   /home/delahantyj@hhmi.org/gitrepos/metazebrobot/deploy/backup_database.sh
   ```

4. **Check cron service is running**:
   ```bash
   systemctl status cron
   ```

### Network drive not mounted?

If the backup fails because `/groups/...` isn't accessible, the script will log an error. Check that the network drive is mounted:
```bash
ls /groups/ahrens/ahrenslab/jeremy/zebrobot/
```

---

## Restoring from Backup

If you need to restore from a backup:

```bash
# Stop the API service first
sudo systemctl stop metazebrobot-api

# Copy backup over the current database
cp /groups/ahrens/ahrenslab/jeremy/zebrobot/backups/zebrobot_YYYYMMDD_HHMMSS.db /nvme1/zebrobot.db

# Restart the API service
sudo systemctl start metazebrobot-api
```

Replace `YYYYMMDD_HHMMSS` with the timestamp of the backup you want to restore.
