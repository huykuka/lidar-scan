#!/usr/bin/env bash
set -e

# If invoked via `sh setup.sh`, re-run with bash (required for this script).
if [ -z "${BASH_VERSION:-}" ]; then
  exec /bin/bash "$0" "$@"
fi

# Determine the project root directory (one level up from this script)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Build the Docker image
echo "Building Docker image..."
docker build -t sick-build -f "$SCRIPT_DIR/Dockerfile" "$PROJECT_ROOT"

# Parse arguments
CLEAN=false
DO_FRONTEND=true
while [ $# -gt 0 ]; do
    case "$1" in
        --clean)
            CLEAN=true
            shift
            ;;
        --skip-frontend)
            DO_FRONTEND=false
            shift
            ;;
        *)
            shift
            ;;
    esac
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

    # Clean up the temporary container
    docker rm "${CONTAINER_ID}" > /dev/null
    
    echo "Artifacts copied successfully."
else
    echo "Host build directory is not empty and --clean not specified. Skipping copy from image."
fi

# Build and deploy frontend to backend static dir
if [ "$DO_FRONTEND" = true ]; then
    if [ ! -d "$PROJECT_ROOT/web" ]; then
        echo "Frontend directory not found at $PROJECT_ROOT/web. Skipping frontend build."
    else
        if ! command -v npm >/dev/null 2>&1; then
            echo "npm not found. Install Node.js/npm or rerun with --skip-frontend."
            exit 1
        fi

        echo "Building frontend and deploying to app/static..."
        WEB_DIR="$PROJECT_ROOT/web"
        STATIC_DIR="$PROJECT_ROOT/app/static"
        DIST_DIR="$WEB_DIR/dist/web"

        ( 
          cd "$WEB_DIR"


          if [ -f package-lock.json ]; then
              npm ci
          else
              npm install
          fi

          # Build production assets
          npm run build -- --configuration production
        )

        # Deploy build artifacts into the backend static directory
        mkdir -p "$STATIC_DIR"
        rm -rf "$STATIC_DIR"/*

        if [ -d "$DIST_DIR/browser" ] && [ -n "$(ls -A "$DIST_DIR/browser" 2>/dev/null)" ]; then
            cp -a "$DIST_DIR/browser/." "$STATIC_DIR/"
        elif [ -d "$DIST_DIR" ] && [ -n "$(ls -A "$DIST_DIR" 2>/dev/null)" ]; then
            cp -a "$DIST_DIR/." "$STATIC_DIR/"
        else
            echo "Frontend build output not found at $DIST_DIR."
            exit 1
        fi

        # Keep a tracked placeholder for the directory structure.
        # app/static/* is gitignored except for this file.
        : > "$STATIC_DIR/.gitkeep"
    fi
fi
