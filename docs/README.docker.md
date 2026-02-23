# Docker Deployment Guide

This guide explains how to build and run the LiDAR Standalone application using Docker.

## Quick Start

### Production Mode

```bash
# Build and start the application
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the application
docker-compose down
```

The application will be available at `http://localhost:8005`

### Development Mode

```bash
# Start in development mode with hot-reload
docker-compose --profile dev up lidar-standalone-dev

# Stop development mode
docker-compose --profile dev down
```

## Configuration

### Environment Variables

Edit `docker-compose.yml` to configure the application:

```yaml
environment:
  # API Settings
  - HOST=0.0.0.0
  - PORT=8005
  - DEBUG=false
  
  # LIDAR Settings
  - LIDAR_MODE=sim         # "sim" or "real"
  - LIDAR_IP=192.168.100.123
  - LIDAR_PCD_PATH=/app/data/test.pcd
  - LIDAR_LAUNCH=/app/launch/sick_multiscan.launch
```

### Hardware Mode (Real LiDAR)

To connect to real LiDAR hardware:

1. Set `LIDAR_MODE=real` in `docker-compose.yml`
2. Update `LIDAR_IP` to your LiDAR device IP
3. Ensure network access to the LiDAR device
4. Add network mode if needed:

```yaml
services:
  lidar-standalone:
    network_mode: host  # For direct hardware access
```

### Simulation Mode (PCD Files)

To use simulation mode with PCD files:

1. Set `LIDAR_MODE=sim` in `docker-compose.yml`
2. Place your PCD files in the `./data` directory
3. Update `LIDAR_PCD_PATH=/app/data/your-file.pcd`

## Volume Mounts

The following directories are mounted as volumes:

- `./config` - SQLite database persistence
- `./debug_data` - Debug output files
- `./data` - PCD files for simulation
- `./launch` - Launch files for real hardware

## Building

### Build Production Image

```bash
docker-compose build
```

### Build with Custom Tag

```bash
docker build -t lidar-standalone:latest .
```

### Multi-platform Build

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t lidar-standalone:latest .
```

## Running

### Production Container

```bash
# Start in detached mode
docker-compose up -d

# View logs
docker-compose logs -f lidar-standalone

# Restart
docker-compose restart lidar-standalone

# Stop
docker-compose down
```

### Run Single Container

```bash
docker run -d \
  --name lidar-standalone \
  -p 8005:8005 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/debug_data:/app/debug_data \
  -e LIDAR_MODE=sim \
  lidar-standalone:latest
```

## Health Checks

The container includes a health check that monitors the API status endpoint:

```bash
# Check container health
docker inspect --format='{{.State.Health.Status}}' lidar-standalone

# View health check logs
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' lidar-standalone
```

## Troubleshooting

### Check Logs

```bash
# All logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100 lidar-standalone

# Only errors
docker-compose logs -f | grep ERROR
```

### Access Container Shell

```bash
docker-compose exec lidar-standalone /bin/bash
```

### Check Process Status

```bash
docker-compose exec lidar-standalone ps aux
```

### Verify Network Connectivity

```bash
# Test LiDAR device connectivity from container
docker-compose exec lidar-standalone ping 192.168.100.123
```

### Database Issues

```bash
# Remove database to reset (WARNING: loses all data)
rm -f config/data.db
docker-compose restart lidar-standalone
```

## Performance Optimization

### Resource Limits

Add resource constraints in `docker-compose.yml`:

```yaml
services:
  lidar-standalone:
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 4G
        reservations:
          cpus: '2.0'
          memory: 2G
```

### Shared Memory for Open3D

If experiencing Open3D memory issues:

```yaml
services:
  lidar-standalone:
    shm_size: '2gb'
```

## Security

### Non-root User

For production, consider running as non-root user (add to Dockerfile):

```dockerfile
RUN useradd -m -u 1000 lidar && \
    chown -R lidar:lidar /app
USER lidar
```

### Read-only Filesystem

```yaml
services:
  lidar-standalone:
    read_only: true
    tmpfs:
      - /tmp
      - /app/debug_data
```

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Build Docker image
  run: docker build -t lidar-standalone:${{ github.sha }} .

- name: Run tests
  run: docker run --rm lidar-standalone:${{ github.sha }} pytest

- name: Push to registry
  run: |
    docker tag lidar-standalone:${{ github.sha }} registry/lidar-standalone:latest
    docker push registry/lidar-standalone:latest
```

## Monitoring

### Prometheus Metrics (Optional)

Add prometheus client to monitor the application. Install in requirements.txt:

```
prometheus-client
```

Expose metrics endpoint and scrape with Prometheus.

## Updates

### Update Application

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose up -d --build
```

### Update Dependencies

```bash
# Rebuild without cache
docker-compose build --no-cache
docker-compose up -d
```
