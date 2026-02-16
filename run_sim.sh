#!/bin/bash
# Set up library paths (still good to have even for sim)
export LD_LIBRARY_PATH=.:./build:$LD_LIBRARY_PATH
export PYTHONPATH=.:./sick-scan-api/api:$PYTHONPATH

# Configure for Simulation Mode
export LIDAR_MODE=real
export LIDAR_PCD_PATH=./1769503697-362730026.pcd

# Allow overriding PORT
export PORT=${PORT:-8004}
export DEBUG=true

echo "----------------------------------------------------------------"
echo "Starting Simulation Mode with PCD: $LIDAR_PCD_PATH"
echo "Frontend available at: http://localhost:$PORT/static/index.html"
echo "----------------------------------------------------------------"

python3 main.py
