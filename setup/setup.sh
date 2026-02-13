#!/bin/bash
set -e

# Determine the project root directory (one level up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Build the Docker image
echo "Building Docker image..."
docker build -t lidar-standalone -f "$SCRIPT_DIR/Dockerfile" "$PROJECT_ROOT"

# Ensure the build directory exists on the host
mkdir -p "$PROJECT_ROOT/build"

# Run the container
# - Mount the project root's 'build' directory to '/workspace/build' in the container
# - Mount the current directory (project root) to /workspace/app if needed, 
#   but specifically requested was mounting build folder. 
#   We interpret "mount the build folder to ../build" as mounting the host's ../build to container's build.
echo "Running container..."
docker run -it --rm \
    -v "$PROJECT_ROOT/build":/workspace/build \
    lidar-standalone bash