#!/bin/bash
set -e

# Determine the project root directory (one level up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Build the Docker image
echo "Building Docker image..."
docker build -t sick-build -f "$SCRIPT_DIR/Dockerfile" "$PROJECT_ROOT"

# Parse arguments
CLEAN=false
for arg in "$@"; do
    if [ "$arg" == "--clean" ]; then
        CLEAN=true
        shift
    fi
done

# Ensure directories exist
mkdir -p "$PROJECT_ROOT/build"
mkdir -p "$PROJECT_ROOT/launch"
mkdir -p "$PROJECT_ROOT/sick-scan-api"

# Clean directories if requested
if [ "$CLEAN" = true ]; then
    echo "Cleaning host directories..."
    rm -rf "$PROJECT_ROOT/build/"*
    rm -rf "$PROJECT_ROOT/launch/"*
    rm -rf "$PROJECT_ROOT/sick-scan-api/"*
fi

# Check if we need to copy artifacts (if clean was requested OR build dir is empty)
if [ "$CLEAN" = true ] || [ -z "$(ls -A "$PROJECT_ROOT/build")" ]; then
    if [ "$CLEAN" = true ]; then
        echo "Directories cleaned. Copying pre-built artifacts..."
    else
        echo "Host build directory is empty. Copying pre-built artifacts..."
    fi
    
    # Create a temporary container from the image
    CONTAINER_ID=$(docker create sick-build)
    
    # Copy the build directory contents from the container to the host
    docker cp "${CONTAINER_ID}:/workspace/build/." "$PROJECT_ROOT/build/"
    docker cp "${CONTAINER_ID}:/workspace/sick_scan_xd/launch/." "$PROJECT_ROOT/launch/"
    docker cp "${CONTAINER_ID}:/workspace/sick_scan_xd/python/." "$PROJECT_ROOT/sick-scan-api/"

    # Clean up the temporary container
    docker rm "${CONTAINER_ID}" > /dev/null
    
    echo "Artifacts copied successfully."
else
    echo "Host build directory is not empty and --clean not specified. Skipping copy from image."
fi

