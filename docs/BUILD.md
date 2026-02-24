# Building Lidar Standalone Executables

This guide explains how to build standalone executables for the Lidar Standalone application.

## Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- All dependencies from `requirements.txt` installed
- At least 2GB of free disk space for the build

## Quick Build

The easiest way to build the application is using the provided build script:

```bash
./build.sh
```

This script will:
1. Build the Angular frontend
2. Install Python dependencies
3. Clean previous builds
4. Create the standalone executable with PyInstaller

## Build Output

After a successful build, you'll find:

- **Executable**: `dist/lidar-standalone/lidar-standalone` (Linux)
- **Size**: ~1.4 GB (includes Python runtime, all dependencies, and frontend)
- **Dependencies**: All required libraries are bundled

## Running the Executable

```bash
cd dist/lidar-standalone
./lidar-standalone
```

The application will start on `http://0.0.0.0:8005` by default.

## Creating a Distributable Package

To create a compressed archive for distribution:

```bash
cd dist
tar -czf lidar-standalone-linux-x64.tar.gz lidar-standalone/
```

## Manual Build Steps

If you prefer to build manually:

### 1. Build Frontend

```bash
cd web
npm install
npm run build:backend
cd ..
```

### 2. Install Build Tools

```bash
pip install pyinstaller
```

### 3. Build Executable

```bash
pyinstaller --clean lidar-standalone.spec
```

## Build Configuration

The build is configured in `lidar-standalone.spec`:

- **Entry Point**: `standalone.py` (PyInstaller-compatible wrapper)
- **Includes**: 
  - All app modules
  - Frontend static files (`app/static/`)
  - Configuration directory (`config/`)
  - Open3D data files and dependencies
  - All uvicorn/FastAPI/WebSocket dependencies

- **Excludes**: 
  - GUI frameworks (tkinter, PyQt, etc.) - not needed for server app

## Cross-Platform Building

### Windows Executable

To build for Windows, run PyInstaller on a Windows machine with the same spec file. The output will be `lidar-standalone.exe`.

**Note**: Cross-compilation (building Windows .exe on Linux) is not supported by PyInstaller. You must build on the target platform.

### Building on Windows

```powershell
# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build frontend
cd web
npm install
npm run build:backend
cd ..

# Build executable
pyinstaller --clean lidar-standalone.spec
```

The Windows executable will be created at `dist\lidar-standalone\lidar-standalone.exe`.

## Troubleshooting

### Build Takes Too Long

The first build includes many dependencies (Open3D, numpy, plotly, dash, sklearn, etc.) and can take 5-10 minutes. Subsequent builds are faster due to caching.

### "Module not found" Errors

If you encounter missing module errors:

1. Ensure all dependencies are installed: `pip install -r requirements.txt`
2. Check that the module is not in the `excludes` list in the spec file
3. Add the module to `hidden_imports` if PyInstaller doesn't detect it automatically

### Large Executable Size

The executable is large (~1.4 GB) because it includes:
- Python runtime
- Open3D (point cloud processing library)
- Scientific computing libraries (numpy, scipy, pandas)
- Visualization libraries (plotly, dash)
- Machine learning libraries (sklearn)
- Web framework (FastAPI, uvicorn)
- All dependencies

This is normal for Python applications with heavy scientific dependencies.

### Static Files Not Found

If the frontend doesn't load, ensure:
1. `web/dist/web/browser/` exists and contains built files
2. The frontend was built with `npm run build:backend`
3. Files were copied to `app/static/`

## Build Artifacts

After building, you'll have these directories:

- `build/` - Temporary build files (can be deleted)
- `dist/lidar-standalone/` - The complete distributable application
  - `lidar-standalone` - Main executable
  - `_internal/` - Bundled Python runtime and libraries
  
## Distribution

To distribute the application:

1. Package the entire `dist/lidar-standalone/` directory
2. Compress it: `tar -czf lidar-standalone-linux-x64.tar.gz lidar-standalone/`
3. Share the archive with users
4. Users extract and run: `./lidar-standalone`

**Important**: The `_internal/` directory must stay with the executable - they work together as a unit.

## Environment Variables

The built executable respects these environment variables:

- `PORT` - Server port (default: 8005)
- `HOST` - Bind address (default: 0.0.0.0)
- `DEBUG` - Enable debug mode (default: false)

Example:
```bash
PORT=9000 ./lidar-standalone
```

## Configuration

The executable creates/uses a `config/` directory for:
- SQLite database (`data.db`)
- Lidar configurations
- Fusion pipelines

This directory is created automatically on first run.
