import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    # Get configuration from settings
    port = settings.PORT
    host = settings.HOST

    print(f"Starting {settings.PROJECT_NAME} on {host}:{port}")

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
