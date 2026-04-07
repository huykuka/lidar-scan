#!/bin/bash
set -e

# Change to the root of the project
cd "$(dirname "$0")/.."

timestamp() {
  date +"%Y%m%d%H%M%S"
}

# ------------------------------
# Variables
# ------------------------------
DOCKERFILE="docker/Dockerfile"
DOCKER_USERNAME="010497"   # <-- change this
DOCKER_REPO_NAME="lidar-studio"
TAG_ARMV8="$DOCKER_USERNAME/$DOCKER_REPO_NAME:latest-armv8"


echo "======================================"
echo "Building and deploying ARM v8 (arm64) image..."
echo "======================================"

# ------------------------------
# Build, tag and push ARMv8
# ------------------------------
docker buildx build --platform linux/arm64 -f $DOCKERFILE . -t "$TAG_ARMV8" --push
