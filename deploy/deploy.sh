#!/bin/bash

# ------------------------------
# Login (required)
# ------------------------------
docker login

# ------------------------------
# Set up shared multi-architecture builder
# ------------------------------
echo "======================================"
echo "Setting up shared Buildx cache..."
echo "======================================"
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes || true
docker buildx create --name lidar-builder --use 2>/dev/null || true
docker buildx inspect --bootstrap

# ------------------------------
# Variables
# ------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ------------------------------
# Run architecture deployments
# ------------------------------
bash "$SCRIPT_DIR/deploy_amd.sh"
# bash "$SCRIPT_DIR/deploy_arm.sh"

echo "======================================"
echo "Deployment for all architectures completed!"
echo "======================================"