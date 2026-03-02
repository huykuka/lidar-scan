"""
LiDAR Standalone API Server

A high-performance Point Cloud Processing system with integrated performance monitoring.

Environment Variables:
    LIDAR_ENABLE_METRICS: Enable performance metrics collection (default: true)
                         Set to 'false' to disable for production with zero overhead
    METRICS_BROADCAST_HZ: Metrics broadcast frequency in Hz (default: 1)
    HOST: Server host address (default: 0.0.0.0)
    PORT: Server port (default: 8005)
    DEBUG: Enable debug mode with auto-reload (default: false)

CLI Usage:
    python main.py
    
    # Disable metrics for production
    LIDAR_ENABLE_METRICS=false python main.py
    
    # Enable metrics with custom broadcast rate
    LIDAR_ENABLE_METRICS=true METRICS_BROADCAST_HZ=2 python main.py
"""

import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    # Get configuration from settings
    port = settings.PORT
    host = settings.HOST

    print(f"Starting {settings.PROJECT_NAME} on {host}:{port}")
    print(f"Performance metrics: {'enabled' if settings.LIDAR_ENABLE_METRICS else 'disabled'}")

    # If reload is enabled, restrict watch scope to backend code only.
    # This avoids uvicorn reloading when frontend/test files change.
    reload_enabled = bool(settings.DEBUG)
    reload_dirs = None
    if reload_enabled:
        try:
            from pathlib import Path

            repo_root = Path(__file__).resolve().parent
            reload_dirs = [str(repo_root / "app")]
        except Exception:
            reload_dirs = ["app"]

    uvicorn.run(
        "app.app:app",
        host=host,
        port=port,
        reload=reload_enabled,
        reload_dirs=reload_dirs,
    )
