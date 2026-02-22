#!/bin/bash
set -e

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "Building Lidar Standalone Application"
echo "=========================================="
echo ""

# Step 1: Build Angular Frontend
echo "[1/5] Building Angular frontend..."
cd web
npm run build:backend
cd ..
echo "✓ Frontend build complete"
echo ""

# Step 2: Ensure all Python dependencies are installed
echo "[2/5] Installing Python dependencies..."
pip install -r requirements.txt
pip install pyinstaller
echo "✓ Dependencies installed"
echo ""

# Step 3: Freeze dependencies to capture all installed packages
echo "[3/5] Freezing dependencies..."
pip freeze > requirements-frozen.txt
echo "✓ Frozen dependencies saved to requirements-frozen.txt ($(wc -l < requirements-frozen.txt) packages)"
echo ""

# Step 4: Clean previous build
echo "[4/5] Cleaning previous builds..."
rm -rf build dist
echo "✓ Clean complete"
echo ""

# Step 5: Build executable with PyInstaller
echo "[5/5] Building executable with PyInstaller..."
pyinstaller --clean scripts/lidar-standalone.spec
echo "✓ Build complete"
echo ""

# Summary
echo "=========================================="
echo "Build Summary"
echo "=========================================="
if [ -f "dist/lidar-standalone/lidar-standalone" ]; then
    SIZE=$(du -sh dist/lidar-standalone | cut -f1)
    echo "✓ Executable: dist/lidar-standalone/lidar-standalone"
    echo "✓ Total size: $SIZE"
    echo ""
    echo "To run the application:"
    echo "  cd dist/lidar-standalone"
    echo "  ./lidar-standalone"
    echo ""
    echo "To create a distributable archive:"
    echo "  cd dist"
    echo "  tar -czf lidar-standalone-linux-x64.tar.gz lidar-standalone/"
else
    echo "✗ Build failed - executable not found"
    exit 1
fi
