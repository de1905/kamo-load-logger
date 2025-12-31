# Synology NAS Deployment Guide

Deploy KAMO Load Logger on a Synology NAS using Container Manager.

## Requirements

- Synology NAS with Container Manager (Docker) support
- DSM 7.0 or newer recommended
- At least 1GB RAM available

## Step 1: Enable Container Manager

1. Open **Package Center**
2. Search for **Container Manager**
3. Click **Install**

## Step 2: Create Folder Structure

1. Open **File Station**
2. Navigate to your preferred volume (e.g., `/volume1`)
3. Create folder: `docker/kamo-load-logger`
4. Inside that, create: `data` subfolder

Full path: `/volume1/docker/kamo-load-logger/data`

## Step 3: Upload Configuration Files

1. Download `.env.example` and `docker-compose.yml` from the repository
2. Upload them to `/volume1/docker/kamo-load-logger/`
3. Rename `.env.example` to `.env`

## Step 4: Configure Environment

1. Open **File Station**
2. Right-click on `.env` → **Edit with Text Editor**
3. Update the configuration:

```env
API_KEY=your-secure-random-string-here
TZ=America/Chicago
POLL_INTERVAL_MINUTES=30
```

4. Save and close

## Step 5: Deploy via Container Manager

### Option A: Using Docker Compose (DSM 7.2+)

1. Open **Container Manager**
2. Go to **Project**
3. Click **Create**
4. Name: `kamo-load-logger`
5. Path: `/volume1/docker/kamo-load-logger`
6. Source: Select **Use existing docker-compose.yml**
7. Click **Next** and then **Done**

### Option B: Manual Container Setup (Older DSM)

1. Open **Container Manager** → **Registry**
2. Search for `python` and download `python:3.11-slim`
3. Go to **Image** → **Build**
4. Upload the Dockerfile or build locally and export

Since Synology doesn't easily support building, it's easier to:

```bash
# On another machine, build and export
docker build -t kamo-load-logger:latest .
docker save kamo-load-logger:latest > kamo-load-logger.tar

# Upload kamo-load-logger.tar to NAS
# In Container Manager → Image → Add → Add from file
```

Then create container:

1. **Image** → Select `kamo-load-logger` → **Launch**
2. **Container Name**: `kamo-load-logger`
3. **Enable auto-restart**: Yes
4. **Port Settings**: Local 8080 → Container 8080
5. **Volume Settings**:
   - `/volume1/docker/kamo-load-logger/data` → `/app/data`
6. **Environment**:
   - Add all variables from `.env`
7. Click **Apply**

## Step 6: Configure Scheduled Backup

1. Open **Control Panel** → **Task Scheduler**
2. Click **Create** → **Scheduled Task** → **User-defined script**
3. **General**:
   - Task: `KAMO Logger Backup`
   - User: `root`
4. **Schedule**:
   - Run daily at 2:00 AM
5. **Task Settings** → **Run command**:
   ```bash
   docker exec kamo-load-logger /app/scripts/backup.sh
   ```
6. Click **OK**

## Step 7: Verify Installation

1. Open browser to `http://<nas-ip>:8080`
2. You should see the KAMO Load Logger dashboard

## Reverse Proxy with SSL (Optional)

1. Open **Control Panel** → **Login Portal** → **Advanced**
2. Click **Reverse Proxy** → **Create**
3. Configure:
   - Description: `KAMO Logger`
   - Source Protocol: HTTPS
   - Source Hostname: `kamo.yourdomain.com`
   - Source Port: 443
   - Destination: `http://localhost:8080`
4. Enable HSTS if desired

## Updating

1. Pull new image or rebuild
2. In **Container Manager** → **Container**
3. Stop `kamo-load-logger`
4. **Action** → **Reset** (keeps volumes)
5. Start container

## Troubleshooting

### View Logs
1. **Container Manager** → **Container**
2. Select `kamo-load-logger`
3. Click **Details** → **Log**

### Container Won't Start
- Check port 8080 isn't used by another service
- Verify volume paths exist and have correct permissions

### Permission Errors
```bash
# SSH into NAS
sudo chown -R 1000:1000 /volume1/docker/kamo-load-logger/data
```

### Database Issues
Stop container, delete `data/kamo_load.db`, restart (will recreate empty database)
