import asyncio
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager

from app.core.logging_config import get_logger
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import router as api_router
from app.core.config import settings
from app.db.migrate import ensure_schema
from app.db.session import init_engine
from app.services.nodes.instance import node_manager
from app.services.shared.recorder import get_recorder
from app.services.status_broadcaster import start_status_broadcaster, stop_status_broadcaster
from app.services.websocket.manager import manager

logger = get_logger("app")

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
    
    # Initialize recorder and connect to WebSocket manager
    recorder = get_recorder()
    manager.recorder = recorder

    node_manager.load_config()
    node_manager.start(asyncio.get_running_loop())
    
    # Start status broadcaster
    start_status_broadcaster()

    yield

    # Shutdown
    stop_status_broadcaster()
    
    # Stop all active recordings
    await recorder.stop_all_recordings()
    
    node_manager.stop()

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

# Mount recordings directory statically
recordings_dir = Path("recordings")
recordings_dir.mkdir(parents=True, exist_ok=True)
app.mount("/recordings", StaticFiles(directory=str(recordings_dir)), name="recordings")

# Serve Angular SPA (and assets) from app/static at root.
# Keep this mount LAST so API routes (e.g. /lidars, /ws/*, /status) take precedence.
static_dir = get_static_path()
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="spa")

    @app.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            # If the request is not for the API or recordings, return the SPA index.html
            if not request.url.path.startswith("/api/") and not request.url.path.startswith("/recordings/"):
                index_path = Path(static_dir) / "index.html"
                if index_path.exists():
                    return FileResponse(index_path)
                    
        # Otherwise, fall back to standard JSON response
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        
else:
    logger.warning(f"Static directory not found at {static_dir}")
