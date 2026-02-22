# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Get project root (parent of scripts/)
# SPECPATH is set by PyInstaller to the absolute path of the directory containing this spec file
spec_dir = Path(SPECPATH).resolve()  # Ensure it's absolute
project_root = spec_dir.parent  # scripts/ -> project root

print(f"DEBUG: SPECPATH = {SPECPATH}")
print(f"DEBUG: spec_dir = {spec_dir}")
print(f"DEBUG: project_root = {project_root}")
print(f"DEBUG: standalone.py path = {project_root / 'scripts' / 'standalone.py'}")


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
    ] + open3d_datas,
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
