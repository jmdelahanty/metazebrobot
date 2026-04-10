# MetaZebrobot Web/API Service Guide

This guide explains how to set up and manage the MetaZebrobot web/API server as
a systemd service.

## Initial Setup

### Step 1: Copy service file to systemd directory
```bash
sudo cp deploy/metazebrobot-api.service /etc/systemd/system/
```

### Step 2: Reload systemd to recognize new service
```bash
sudo systemctl daemon-reload
```

### Step 3: Enable service to start on boot
```bash
sudo systemctl enable metazebrobot-api
```

### Step 4: Start the service
```bash
sudo systemctl start metazebrobot-api
```

### Step 5: Verify it's running
```bash
sudo systemctl status metazebrobot-api
```

---

## Managing the Service

| Command | Description |
|---------|-------------|
| `sudo systemctl start metazebrobot-api` | Start the service |
| `sudo systemctl stop metazebrobot-api` | Stop the service |
| `sudo systemctl restart metazebrobot-api` | Restart (e.g., after code changes) |
| `sudo systemctl status metazebrobot-api` | Check status + recent log output |
| `sudo systemctl enable metazebrobot-api` | Enable auto-start on boot |
| `sudo systemctl disable metazebrobot-api` | Disable auto-start on boot |

---

## Viewing Logs

| Command | Description |
|---------|-------------|
| `sudo journalctl -u metazebrobot-api -f` | Follow live logs (Ctrl+C to exit) |
| `sudo journalctl -u metazebrobot-api -n 50` | View last 50 log lines |
| `sudo journalctl -u metazebrobot-api --since "1 hour ago"` | Logs from last hour |
| `sudo journalctl -u metazebrobot-api --since today` | Today's logs |

---

## Testing the API

```bash
# Browser entry points
# http://localhost:8000/
# http://localhost:8000/dishes/new

# Health check (no database)
curl http://localhost:8000/health

# Health check with database verification
curl http://localhost:8000/health?check_db=true

# List all crosses
curl http://localhost:8000/crosses

# List crosses with active dishes only
curl "http://localhost:8000/crosses?has_active_dishes=true"

# Get dishes for a specific cross
curl "http://localhost:8000/dishes?cross_id=15180"

# Get active dishes for a specific cross
curl "http://localhost:8000/dishes?cross_id=15180&status=active"

# Get a single cross with its dishes
curl "http://localhost:8000/crosses/15180?include_dishes=true"
```

---

## Troubleshooting

### Service won't start
```bash
# Check what went wrong
sudo journalctl -u metazebrobot-api -n 100

# Common issues:
# - Wrong paths in service file
# - Database file doesn't exist
# - Port 8000 already in use
```

### Check if port is in use
```bash
sudo lsof -i :8000
```

### After updating the service file
```bash
sudo cp deploy/metazebrobot-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart metazebrobot-api
```

---

## Configuration

The service file is at: `/etc/systemd/system/metazebrobot-api.service`

Key settings:
- **Database path**: `/nvme1/zebrobot.db`
- **Port**: 8000
- **Bind address**: `127.0.0.1` in the checked-in unit file
- **LAN access**: add `--lab-network` to `ExecStart` only if you intentionally want other machines to connect
- **Auto-restart**: Yes, on failure (5 second delay)

---

## API Endpoints Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing page for the web UI |
| `/dishes/new` | GET | Dish creation form |
| `/dishes/new` | POST | Create a dish from the web form |
| `/health` | GET | Health check |
| `/health?check_db=true` | GET | Health check with DB verification |
| `/dishes` | GET | List dishes (params: status, cross_id, limit, offset) |
| `/dishes/{dish_id}` | GET | Get single dish (param: include_checks) |
| `/crosses` | GET | List crosses (params: has_active_dishes, limit, offset) |
| `/crosses/{cross_id}` | GET | Get single cross (param: include_dishes) |
