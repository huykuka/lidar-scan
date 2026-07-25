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
DOCKER_USERNAME="010497"   # <-- change this

HOST_ARCH="$(uname -m)"
if [[ "$HOST_ARCH" != "x86_64" && "$HOST_ARCH" != "amd64" ]]; then
  echo "Error: this deploy script only supports amd64 hosts (detected: $HOST_ARCH)."
  exit 1
fi

# Read versions from the source manifests
BE_VERSION=$(grep -m1 '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
FE_VERSION=$(grep -m1 '"version"' web/package.json | sed 's/.*"version": "\([^"]*\)".*/\1/')

echo "======================================"
echo "Backend version : ${BE_VERSION}"
echo "Frontend version: ${FE_VERSION}"
echo "======================================"

# ------------------------------
# Backend — lidar-studio-core
# ------------------------------
CORE_REPO="$DOCKER_USERNAME/lidar-studio-core"
echo ""
echo "Building and deploying lidar-studio-core..."
docker build \
  --platform linux/amd64 \
  -f docker/Dockerfile.backend \
  -t "$CORE_REPO:latest" \
  -t "$CORE_REPO:$BE_VERSION" \
  .
docker push "$CORE_REPO:latest"
docker push "$CORE_REPO:$BE_VERSION"
echo "Pushed $CORE_REPO:$BE_VERSION and :latest"

# ------------------------------
# Frontend — lidar-studio-ui
# ------------------------------
UI_REPO="$DOCKER_USERNAME/lidar-studio-ui"
echo ""
echo "Building and deploying lidar-studio-ui..."
docker build \
  --platform linux/amd64 \
  -f docker/Dockerfile.frontend \
  -t "$UI_REPO:latest" \
  -t "$UI_REPO:$FE_VERSION" \
  .
docker push "$UI_REPO:latest"
docker push "$UI_REPO:$FE_VERSION"
echo "Pushed $UI_REPO:$FE_VERSION and :latest"
