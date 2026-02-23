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

# Step 4: Backup SICK scan driver folders (build/, launch/, sick-scan-api/) if they exist in PyInstaller build/dist
echo "[4/7] Backing up SICK scan driver folders..."
BACKUP_DIR=$(mktemp -d)

# Note: PyInstaller creates its own build/ and dist/ directories
# We want to preserve the SICK driver's build/ folder which should NOT be in PyInstaller's build/
# The SICK driver folders are in project root and will be included by PyInstaller via spec file

# Check for existing PyInstaller build artifacts (unlikely to have our folders, but just in case)
if [ -d "dist/lidar-standalone/sick-scan-api" ]; then
    cp -r dist/lidar-standalone/sick-scan-api "$BACKUP_DIR/dist-sick-scan-api"
    echo "  ✓ Backed up dist/lidar-standalone/sick-scan-api"
fi
if [ -d "dist/lidar-standalone/build" ]; then
    cp -r dist/lidar-standalone/build "$BACKUP_DIR/dist-build"
    echo "  ✓ Backed up dist/lidar-standalone/build"
fi
if [ -d "dist/lidar-standalone/launch" ]; then
    cp -r dist/lidar-standalone/launch "$BACKUP_DIR/dist-launch"
    echo "  ✓ Backed up dist/lidar-standalone/launch"
fi

echo "✓ Backup complete"
echo ""

# Step 5: Clean previous PyInstaller build
echo "[5/7] Cleaning previous PyInstaller builds..."
# Only clean PyInstaller's build and dist directories
# The SICK driver folders (build/, launch/, sick-scan-api/) in project root should remain
if [ -d "build" ]; then
    # Check if this is PyInstaller's build dir (contains .toc files)
    if ls build/*.toc >/dev/null 2>&1 || ls build/*/*.toc >/dev/null 2>&1; then
        rm -rf build
        echo "  ✓ Removed PyInstaller build directory"
    else
        echo "  ℹ Skipping build/ (appears to be SICK driver build folder, not PyInstaller)"
    fi
fi
rm -rf dist
echo "✓ Clean complete"
echo ""

# Step 6: Build executable with PyInstaller
echo "[6/7] Building executable with PyInstaller..."
# PyInstaller will automatically include build/, launch/, and sick-scan-api/ via the spec file
# Use separate directories to avoid conflicts with SICK driver's build/ folder
pyinstaller --clean \
  --workpath=scripts/build \
  --distpath=dist \
  scripts/lidar-standalone.spec
echo "✓ Build complete"
echo ""

# Step 7: Verify SICK scan driver folders were included
echo "[7/7] Verifying SICK scan driver folders..."
MISSING_FOLDERS=()

if [ ! -d "dist/lidar-standalone/sick-scan-api" ]; then
    MISSING_FOLDERS+=("sick-scan-api")
    echo "  ⚠ Warning: sick-scan-api folder not found in dist/lidar-standalone/"
fi

if [ ! -d "dist/lidar-standalone/build" ]; then
    MISSING_FOLDERS+=("build")
    echo "  ⚠ Warning: build folder not found in dist/lidar-standalone/"
fi

if [ ! -d "dist/lidar-standalone/launch" ]; then
    MISSING_FOLDERS+=("launch")
    echo "  ⚠ Warning: launch folder not found in dist/lidar-standalone/"
fi

if [ ${#MISSING_FOLDERS[@]} -eq 0 ]; then
    echo "  ✓ All SICK scan driver folders present:"
    echo "    - sick-scan-api/"
    echo "    - build/"
    echo "    - launch/"
else
    echo ""
    echo "  ⚠ Missing folders: ${MISSING_FOLDERS[*]}"
    echo ""
    echo "  To fix this, make sure you've run setup.sh first:"
    echo "    cd setup && ./setup.sh"
    echo ""
    echo "  This will populate the required folders:"
    echo "    - sick-scan-api/ (SICK driver Python API)"
    echo "    - build/ (compiled SICK driver binaries)"
    echo "    - launch/ (driver configuration files)"
fi

# Clean up backup
rm -rf "$BACKUP_DIR"
echo "✓ Verification complete"
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
