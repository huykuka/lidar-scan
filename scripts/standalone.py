#!/usr/bin/env python3
"""
Standalone entry point for PyInstaller builds.
This script initializes the FastAPI app and runs it with uvicorn.
"""
import sys
import os

# When running from PyInstaller, adjust paths
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle
    bundle_dir = sys._MEIPASS
    # Add the bundle directory to sys.path
    sys.path.insert(0, bundle_dir)

# Now import uvicorn and other dependencies
import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    # Get configuration from settings
    port = settings.PORT
    host = settings.HOST

    print(f"Starting {settings.PROJECT_NAME} on {host}:{port}")

    # Import the app directly to avoid string-based import issues
    from app.app import app

    # Run uvicorn with the app instance directly
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )
