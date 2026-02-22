import asyncio
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import router as api_router
from app.core.config import settings
from app.db.migrate import ensure_schema
from app.db.session import init_engine
from app.services.lidar.instance import lidar_service


def get_static_path():
    """Get the correct static files path for both development and PyInstaller builds."""
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        base_path = Path(sys._MEIPASS)
    else:
        # Running in development
        base_path = Path(__file__).parent.parent
    
    static_path = base_path / "app" / "static"
    return str(static_path)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Startup
    engine = init_engine()
    ensure_schema(engine)

    lidar_service.load_config()
    lidar_service.start(asyncio.get_running_loop())

    yield

    # Shutdown
    lidar_service.stop()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend with Modular Pipeline Registry",
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)





# Serve Angular SPA (and assets) from app/static at root.
# Keep this mount LAST so API routes (e.g. /lidars, /ws/*, /status) take precedence.
static_dir = get_static_path()
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="spa")
else:
    print(f"Warning: Static directory not found at {static_dir}")
