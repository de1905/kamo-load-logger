# Raspberry Pi Deployment Guide

Deploy KAMO Load Logger on a Raspberry Pi 3B+ or newer.

## Requirements

- Raspberry Pi 3B+ or newer (4GB+ RAM recommended for Pi 4)
- Raspberry Pi OS (64-bit recommended)
- External USB storage recommended for data persistence
- Stable internet connection

## Step 1: Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group
sudo usermod -aG docker $USER

# Log out and back in, then verify
docker --version
```

## Step 2: Install Docker Compose

```bash
# Install docker-compose plugin
sudo apt install docker-compose-plugin

# Verify
docker compose version
```

## Step 3: Clone Repository

```bash
# Create directory for the project
mkdir -p ~/docker
cd ~/docker

# Clone the repository
git clone https://github.com/yourusername/kamo-load-logger.git
cd kamo-load-logger
```

## Step 4: Configure

```bash
# Copy environment template
cp .env.example .env

# Generate a random API key
API_KEY=$(openssl rand -hex 32)
echo "Generated API key: $API_KEY"

# Edit configuration
nano .env
```

Update these values in `.env`:
```
API_KEY=<paste your generated key>
TZ=America/Chicago
```

## Step 5: External Storage (Recommended)

For better performance and longevity, store data on external USB storage:

```bash
# Find your USB drive
lsblk

# Mount it (assuming /dev/sda1)
sudo mkdir -p /mnt/usb
sudo mount /dev/sda1 /mnt/usb

# Add to fstab for auto-mount
echo "/dev/sda1 /mnt/usb ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab

# Create data directory
sudo mkdir -p /mnt/usb/kamo-logger/data
sudo chown -R $USER:$USER /mnt/usb/kamo-logger

# Update docker-compose.yml to use external storage
# Change volumes section to:
#   - /mnt/usb/kamo-logger/data:/app/data
```

## Step 6: Build and Start

```bash
# Build the image (takes a few minutes on Pi)
docker compose build

# Start the service
docker compose up -d

# Check logs
docker compose logs -f
```

## Step 7: Auto-Start on Boot

Docker containers with `restart: unless-stopped` will auto-start. To ensure Docker starts on boot:

```bash
sudo systemctl enable docker
```

## Step 8: Verify Installation

```bash
# Check container is running
docker ps

# Check health
curl http://localhost:8080/api/health

# Access dashboard
# Open browser to http://<pi-ip>:8080
```

## Performance Tips

1. **Use 64-bit OS**: Better memory handling for larger databases
2. **External Storage**: Reduces SD card wear
3. **Increase Swap**: If running on 1GB RAM Pi
   ```bash
   sudo dphys-swapfile swapoff
   sudo nano /etc/dphys-swapfile  # Set CONF_SWAPSIZE=2048
   sudo dphys-swapfile setup
   sudo dphys-swapfile swapon
   ```

## Scheduled Backups

Add a cron job for daily backups:

```bash
# Edit crontab
crontab -e

# Add this line (runs at 2 AM daily)
0 2 * * * docker exec kamo-load-logger /app/scripts/backup.sh >> /var/log/kamo-backup.log 2>&1
```

## Updating

```bash
cd ~/docker/kamo-load-logger
git pull
docker compose build
docker compose up -d
```

## Troubleshooting

### Container won't start
```bash
docker compose logs
```

### Database locked errors
```bash
# Stop container, then restart
docker compose down
docker compose up -d
```

### Out of memory
```bash
# Check memory usage
free -h

# Increase swap or reduce poll interval in .env
```

### Find Pi's IP address
```bash
hostname -I
```
