#!/bin/bash

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
bash "$SCRIPT_DIR/deploy_amd.sh"

echo "======================================"
echo "Deployment for all architectures completed!"
echo "======================================"