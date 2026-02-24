# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Get project root (parent of scripts/)
# SPECPATH is set by PyInstaller to the absolute path of the directory containing this spec file
spec_dir = Path(SPECPATH).resolve()  # Ensure it's absolute
project_root = spec_dir.parent  # scripts/ -> project root

# Check if sick-scan-api, build, and launch folders exist and should be included
# These folders are created by setup.sh from Docker and contain SICK scan driver files
sick_scan_folders = []

# Note: We include the SICK driver's build folder (not PyInstaller's build folder)
build_path = project_root / 'build'
if build_path.exists() and any(build_path.iterdir()):
    # Only include if it doesn't look like PyInstaller's build dir
    if not any((build_path / 'Analysis-00.toc').exists() for _ in [1]):
        sick_scan_folders.append((str(build_path), 'build'))
        print(f"INFO: Including SICK driver build folder from {build_path}")

launch_path = project_root / 'launch'
if launch_path.exists() and any(launch_path.iterdir()):
    sick_scan_folders.append((str(launch_path), 'launch'))
    print(f"INFO: Including launch folder from {launch_path}")


block_cipher = None

# Collect Open3D data files
open3d_datas = collect_data_files('open3d')

# Collect all submodules
hidden_imports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'websockets',
    'websockets.legacy',
    'websockets.legacy.server',
    'sqlalchemy.ext.baked',
]

# Collect all app submodules
hidden_imports += collect_submodules('app')

a = Analysis(
    [str(project_root / 'scripts' / 'standalone.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / 'app' / 'static'), 'app/static'),  # Include frontend static files
        (str(project_root / 'config'), 'config'),  # Include config directory
        (str(project_root / 'app'), 'app'),  # Include entire app directory as data
    ] + open3d_datas + sick_scan_folders,  # Add sick-scan-api, build, and launch folders if they exist
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='lidar-standalone',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='lidar-standalone',
)
