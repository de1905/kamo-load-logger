# KAMO Load Logger

A production-grade Docker service that polls the KAMO Power API, stores historical load data, and provides a REST API for data access.

## Features

- **Automated Data Collection**: Polls KAMO Power API every 5 minutes (configurable)
- **Historical Storage**: SQLite database with unlimited retention
- **Deduplication**: Automatically handles duplicate data points
- **REST API**: Full API for querying historical data
- **Web Dashboard**: Monitor import status and database statistics
- **Data Inspector**: View load data like the iOS app with charts
- **Database Tables Viewer**: Browse all database tables and records
- **Email Notifications**: Alerts on import failures
- **Backup/Restore**: Scripts for data backup and migration
- **Multi-Platform**: Runs on x86_64 and ARM64 (Raspberry Pi)

## KAMO API Polling Strategy

The KAMO Power API provides two types of data:

| Endpoint | Data Type | KAMO Update Frequency | Notes |
|----------|-----------|----------------------|-------|
| `/api/areagrid/{id}` | Load history | Hourly | ~12 hours lookback of actual load |
| `/api/arealoadtable/{id}` | Substation snapshot | ~3 minutes | Real-time kW, kVAR, PF per substation |

**Default polling: Every 5 minutes** at standardized timestamps (:00, :05, :10, :15, etc.)

This captures:
- Every hourly load data point
- ~60% of substation updates (good balance of resolution vs. API load)

| Poll Interval | Substation Records/Month | Configuration |
|---------------|--------------------------|---------------|
| 5 min (default) | ~120,000 | `POLL_INTERVAL_MINUTES=5` |
| 10 min | ~60,000 | `POLL_INTERVAL_MINUTES=10` |
| 15 min | ~40,000 | `POLL_INTERVAL_MINUTES=15` |
| 30 min | ~20,000 | `POLL_INTERVAL_MINUTES=30` |

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/yourusername/kamo-load-logger.git
cd kamo-load-logger

# Create environment file
cp .env.example .env

# Edit .env and set your API key
nano .env
```

### 2. Start with Docker Compose

```bash
docker-compose up -d
```

### 3. Access the Dashboard

Open http://localhost:8080 in your browser.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_KEY` | Yes | - | API key for protected endpoints |
| `POLL_INTERVAL_MINUTES` | No | 5 | How often to poll KAMO API (5, 10, 15, or 30 for aligned timestamps) |
| `TZ` | No | America/Chicago | Timezone (all timestamps stored in Central Time) |
| `SMTP_HOST` | No | - | SMTP server for notifications |
| `SMTP_PORT` | No | 587 | SMTP port |
| `SMTP_USER` | No | - | SMTP username |
| `SMTP_PASSWORD` | No | - | SMTP password |
| `NOTIFICATION_EMAIL` | No | - | Email for alerts |
| `LOG_LEVEL` | No | INFO | Logging verbosity |

## API Endpoints

### Public Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/status` | System status and statistics |
| `GET /api/cooperatives` | List all cooperatives |
| `GET /api/load/current/{area_id}` | Latest load for an area |
| `GET /api/load/history/{area_id}` | Historical load data |
| `GET /api/load/peaks/{area_id}` | Peak load records |
| `GET /api/substations/current/{area_id}` | Latest substation data |
| `GET /api/substations/history/{area_id}` | Historical substation data |

### Protected Endpoints (require X-API-Key header)

| Endpoint | Description |
|----------|-------------|
| `POST /api/import/trigger` | Trigger manual import |
| `GET /api/export/load/{area_id}` | Export load data (CSV/JSON) |
| `GET /api/export/substations/{area_id}` | Export substation data |

### Example API Usage

```bash
# Get current KAMO load
curl http://localhost:8080/api/load/current/20

# Get last 24 hours of history
curl "http://localhost:8080/api/load/history/20?hours=24"

# Trigger manual import
curl -X POST -H "X-API-Key: your-api-key" http://localhost:8080/api/import/trigger

# Export data as CSV
curl -H "X-API-Key: your-api-key" "http://localhost:8080/api/export/load/20?days=7" -o load_data.csv
```

## Cooperative IDs

| ID | Name | Type |
|----|------|------|
| 1 | Ozark Electric | Member |
| 2 | Lake Region Electric | Member |
| 3 | Barry Electric | Member |
| ... | ... | ... |
| 17 | Verdigris Valley Electric | Member |
| 18 | Missouri Region | Aggregate |
| 19 | Oklahoma Region | Aggregate |
| 20 | KAMO Total | Aggregate |

## Backup & Restore

### Create Backup

```bash
# Inside container
docker exec kamo-load-logger /app/scripts/backup.sh

# Or from host (if data directory is mounted)
./scripts/backup.sh
```

### Restore from Backup

```bash
docker exec -it kamo-load-logger /app/scripts/restore.sh backup_file.db
```

### Migrate to New Instance

```bash
# Export from old instance
docker exec kamo-load-logger /app/scripts/migrate.sh export > data_export.sql

# Import to new instance
docker exec -i new-kamo-logger /app/scripts/migrate.sh import < data_export.sql
```

## Deployment Guides

- [Raspberry Pi](docs/raspberry-pi.md)
- [Synology NAS](docs/synology-nas.md)
- [Unraid](docs/unraid.md)

## Development

### Run Locally

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run
uvicorn app.main:app --reload
```

### Run Tests

```bash
pytest
```

## License

MIT License
