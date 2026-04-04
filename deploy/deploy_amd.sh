#!/bin/bash

timestamp() {
  date +"%Y%m%d%H%M%S"
}

# ------------------------------
# Variables
# ------------------------------
DOCKERFILE="docker/Dockerfile"
DOCKER_USERNAME="010497"   # <-- change this
DOCKER_REPO_NAME="lidar-studio"
TAG_LATEST="$DOCKER_USERNAME/$DOCKER_REPO_NAME:latest-amd64"

echo "======================================"
echo "Building and deploying AMD64 image..."
echo "======================================"

# ------------------------------
# Build, tag and push
# ------------------------------
docker build --platform linux/amd64 -f $DOCKERFILE . -t "$TAG_LATEST"
docker push "$TAG_LATEST"
