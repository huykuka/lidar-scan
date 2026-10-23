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

PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

# Multi-arch images need a buildx builder and QEMU/binfmt for foreign targets.
docker buildx inspect lidar-multiarch >/dev/null 2>&1 || docker buildx create --name lidar-multiarch --use
docker buildx use lidar-multiarch
docker run --privileged --rm tonistiigi/binfmt --install all >/dev/null

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
docker buildx build \
  --platform "$PLATFORMS" \
  --push \
  -f docker/Dockerfile.backend \
  -t "$CORE_REPO:latest" \
  -t "$CORE_REPO:$BE_VERSION" \
  .
echo "Pushed $CORE_REPO:$BE_VERSION and :latest"

# ------------------------------
# Frontend — lidar-studio-ui
# ------------------------------
UI_REPO="$DOCKER_USERNAME/lidar-studio-ui"
echo ""
echo "Building and deploying lidar-studio-ui..."
docker buildx build \
  --platform "$PLATFORMS" \
  --push \
  -f docker/Dockerfile.frontend \
  -t "$UI_REPO:latest" \
  -t "$UI_REPO:$FE_VERSION" \
  .
echo "Pushed $UI_REPO:$FE_VERSION and :latest"
