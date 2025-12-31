# Unraid Deployment Guide

Deploy KAMO Load Logger on Unraid using Docker.

## Requirements

- Unraid 6.9 or newer
- Docker enabled
- Community Applications plugin (recommended)

## Step 1: Prepare Directories

1. Open Unraid web UI
2. Go to **Shares** or use terminal:

```bash
mkdir -p /mnt/user/appdata/kamo-load-logger/data
```

## Step 2: Add Container via Docker UI

1. Go to **Docker** tab
2. Click **Add Container**

### Basic Config

| Field | Value |
|-------|-------|
| Name | `kamo-load-logger` |
| Repository | Build from Dockerfile (see below) |
| Network Type | `bridge` |

### Port Mappings

| Container Port | Host Port | Description |
|----------------|-----------|-------------|
| 8080 | 8080 | Web UI & API |

### Volume Mappings

| Container Path | Host Path | Access |
|----------------|-----------|--------|
| `/app/data` | `/mnt/user/appdata/kamo-load-logger/data` | Read/Write |

### Environment Variables

| Variable | Value |
|----------|-------|
| `API_KEY` | `your-secure-api-key` |
| `TZ` | `America/Chicago` |
| `POLL_INTERVAL_MINUTES` | `30` |
| `SMTP_HOST` | (optional) |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | (optional) |
| `SMTP_PASSWORD` | (optional) |
| `NOTIFICATION_EMAIL` | (optional) |

## Step 3: Build the Image

Since Unraid doesn't have a built-in way to build from Dockerfile, you have two options:

### Option A: Build on Another Machine

```bash
# On a machine with Docker
git clone https://github.com/yourusername/kamo-load-logger.git
cd kamo-load-logger
docker build -t kamo-load-logger:latest .
docker save kamo-load-logger:latest | gzip > kamo-load-logger.tar.gz

# Copy to Unraid and import
scp kamo-load-logger.tar.gz root@unraid:/tmp/
```

On Unraid:
```bash
docker load < /tmp/kamo-load-logger.tar.gz
```

### Option B: Use Unraid Terminal

```bash
# SSH into Unraid or use terminal
cd /tmp
git clone https://github.com/yourusername/kamo-load-logger.git
cd kamo-load-logger
docker build -t kamo-load-logger:latest .
```

## Step 4: Create Container Template (Optional)

Create `/boot/config/plugins/dockerMan/templates-user/kamo-load-logger.xml`:

```xml
<?xml version="1.0"?>
<Container version="2">
  <Name>kamo-load-logger</Name>
  <Repository>kamo-load-logger:latest</Repository>
  <Registry/>
  <Network>bridge</Network>
  <Privileged>false</Privileged>
  <Support/>
  <Overview>KAMO Load Logger - Historical load data collection for KAMO Power cooperatives</Overview>
  <Category>Tools:</Category>
  <WebUI>http://[IP]:[PORT:8080]/</WebUI>
  <Icon>https://raw.githubusercontent.com/yourusername/kamo-load-logger/main/icon.png</Icon>
  <ExtraParams/>
  <DateInstalled/>
  <Config Name="Web UI Port" Target="8080" Default="8080" Mode="tcp" Description="Web interface port" Type="Port" Display="always" Required="true" Mask="false">8080</Config>
  <Config Name="Data" Target="/app/data" Default="/mnt/user/appdata/kamo-load-logger/data" Mode="rw" Description="Database storage" Type="Path" Display="always" Required="true" Mask="false">/mnt/user/appdata/kamo-load-logger/data</Config>
  <Config Name="API Key" Target="API_KEY" Default="" Mode="" Description="API key for protected endpoints" Type="Variable" Display="always" Required="true" Mask="true"/>
  <Config Name="Timezone" Target="TZ" Default="America/Chicago" Mode="" Description="Container timezone" Type="Variable" Display="always" Required="false" Mask="false">America/Chicago</Config>
  <Config Name="Poll Interval" Target="POLL_INTERVAL_MINUTES" Default="30" Mode="" Description="Minutes between API polls" Type="Variable" Display="always" Required="false" Mask="false">30</Config>
</Container>
```

## Step 5: Start Container

1. Go to **Docker** tab
2. Find `kamo-load-logger`
3. Click the icon → **Start**

## Step 6: Verify Installation

1. Click the container icon → **WebUI**
   Or open `http://<unraid-ip>:8080`
2. Dashboard should show system status

## Step 7: Scheduled Backups

1. Go to **Settings** → **User Scripts**
2. Click **Add New Script**
3. Name: `KAMO Logger Backup`
4. Edit script:

```bash
#!/bin/bash
docker exec kamo-load-logger /app/scripts/backup.sh
```

5. Set schedule: **Custom** → `0 2 * * *` (2 AM daily)
6. Click **Apply**

## Updating

### Manual Update

```bash
# Pull/build new image
cd /tmp/kamo-load-logger
git pull
docker build -t kamo-load-logger:latest .

# Restart container
docker restart kamo-load-logger
```

### Via Docker UI

1. Stop container
2. Remove container (keep appdata!)
3. Remove old image
4. Rebuild/reimport new image
5. Recreate container with same settings

## Monitoring with Prometheus (Optional)

Add to your Prometheus config:

```yaml
scrape_configs:
  - job_name: 'kamo-logger'
    static_configs:
      - targets: ['<unraid-ip>:8080']
    metrics_path: '/api/health'
```

## Troubleshooting

### View Logs

1. Click container icon → **Logs**

Or via terminal:
```bash
docker logs -f kamo-load-logger
```

### Container Won't Start

Check for port conflicts:
```bash
docker port kamo-load-logger
netstat -tlnp | grep 8080
```

### Permission Issues

```bash
chown -R nobody:users /mnt/user/appdata/kamo-load-logger
chmod -R 755 /mnt/user/appdata/kamo-load-logger
```

### Database Corruption

```bash
# Stop container
docker stop kamo-load-logger

# Backup corrupt DB
mv /mnt/user/appdata/kamo-load-logger/data/kamo_load.db /mnt/user/appdata/kamo-load-logger/data/kamo_load.db.corrupt

# Start container (creates new DB)
docker start kamo-load-logger
```
