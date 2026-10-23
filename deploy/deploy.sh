#!/bin/bash
set -e

# ------------------------------
# Login (required)
# ------------------------------
docker login
# ------------------------------
# Variables
# ------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ------------------------------
# Run architecture deployments
# ------------------------------
bash "$SCRIPT_DIR/deploy_multiarch.sh"

echo "======================================"
echo "Multi-arch (amd64 + arm64) deployment completed!"
echo "  lidar-studio-core (backend)"
echo "  lidar-studio-ui   (frontend)"
echo "======================================"