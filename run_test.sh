#!/bin/bash
# Set up library paths
export LD_LIBRARY_PATH=.:./build:$LD_LIBRARY_PATH
export PYTHONPATH=.:./python/api:$PYTHONPATH

# Run the FastAPI standalone application
# You can override LIDAR_IP and LIDAR_LAUNCH if needed
# export LIDAR_IP=192.168.100.123
# export LIDAR_LAUNCH=./launch/sick_multiscan.launch

python3 main.py
