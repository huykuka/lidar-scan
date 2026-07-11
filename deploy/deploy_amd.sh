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
TAG_LATEST="$DOCKER_USERNAME/$DOCKER_REPO_NAME:latest"

HOST_ARCH="$(uname -m)"
if [[ "$HOST_ARCH" != "x86_64" && "$HOST_ARCH" != "amd64" ]]; then
  echo "Error: this deploy script only supports amd64 hosts (detected: $HOST_ARCH)."
  exit 1
fi

echo "======================================"
echo "Building and deploying AMD64 image..."
echo "======================================"

# ------------------------------
# Build, tag and push
# ------------------------------
docker build --platform linux/amd64 -f $DOCKERFILE . -t "$TAG_LATEST"
docker push "$TAG_LATEST"
