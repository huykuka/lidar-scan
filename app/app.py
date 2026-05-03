import asyncio
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager

from app.core.logging import get_logger
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
from app.services.status_aggregator import start_status_aggregator, stop_status_aggregator
from app.services.websocket.manager import manager

logger = get_logger("app")

# OpenAPI tag definitions for Swagger documentation
OPENAPI_TAGS: list[dict] = [
    {
        "name": "System",
        "description": "Lifecycle control and health checks for the pipeline engine.",
    },
    {
        "name": "Nodes",
        "description": (
            "Read-only access and live-action toggles for DAG processing nodes. "
            "Node creation, update, and deletion is performed atomically via "
            "PUT /api/v1/dag/config. This router exposes list, get, enabled/visible "
            "toggles, status queries, and the reload trigger."
        ),
    },
    {
        "name": "Edges",
        "description": (
            "Read-only access to directed connections between DAG nodes. "
            "Edge creation and deletion is performed atomically via "
            "PUT /api/v1/dag/config. This router exposes only GET /edges."
        ),
    },
    {
        "name": "Configuration",
        "description": (
            "Full-graph import/export and validation. "
            "Allows backup and restore of the entire node-edge topology."
        ),
    },
    {
        "name": "Recordings",
        "description": (
            "Start, stop, list, and download point-cloud recordings. "
            "Recordings capture raw numpy point arrays from any active DAG node."
        ),
    },
    {
        "name": "Logs",
        "description": (
            "Access and stream application logs. "
            "REST endpoint returns paginated log entries; "
            "live streaming is available via the `GET /api/v1/logs/ws` WebSocket (not in REST docs)."
        ),
    },
    {
        "name": "Calibration",
        "description": (
            "ICP multi-sensor calibration. "
            "Trigger alignment computation, accept/reject results, "
            "and rollback to a previous calibration state."
        ),
    },
    {
        "name": "LiDAR",
        "description": (
            "SICK LiDAR device profiles and configuration validation. "
            "Pure in-memory operations — no database or file-system access."
        ),
    },
    {
        "name": "PCD Injection",
        "description": (
            "Multipart PCD file upload for injecting point cloud data into the DAG. "
            "POST a .pcd file to a running PCD Injection node."
        ),
    },
    {
        "name": "Assets",
        "description": "Static image assets served directly from the lidar module bundle.",
    },
    {
        "name": "Topics",
        "description": (
            "Introspection of registered WebSocket topics. "
            "Use `GET /api/v1/topics/capture` for a single-frame HTTP snapshot. "
            "Live streaming requires the `ws://` WebSocket endpoints (not in REST docs)."
        ),
    },
    {
        "name": "DAG",
        "description": (
            "Atomic DAG configuration save/load. "
            "PUT /dag/config replaces all nodes and edges in one transaction and triggers a reload. "
            "GET /dag/config returns the current snapshot with the monotonic config_version."
        ),
    },
]

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
    await node_manager.start(asyncio.get_running_loop())
    
    # Register system topics at startup
    manager.register_topic("shapes")
    
    # Start status aggregator (replaces legacy status_broadcaster)
    start_status_aggregator()
    # Emit initial status for all nodes
    from app.services.status_aggregator import notify_status_change
    for node_id in node_manager.nodes:
        notify_status_change(node_id)

    yield

    # Shutdown
    stop_status_aggregator()
    
    # Stop all active recordings
    await recorder.stop_all_recordings()
    
    node_manager.stop()

app = FastAPI(
    title="LiDAR Standalone API",
    description="""
## LiDAR Standalone REST API

Real-time point-cloud processing pipeline REST interface.

> **Binary streaming** (point cloud XYZ data) is served over the `LIDR` binary WebSocket
> protocol documented separately. Only metadata and control operations are available here.

### Quick-start
1. Check system health: `GET /api/v1/status`
2. List available nodes: `GET /api/v1/nodes`
3. Start a recording: `POST /api/v1/recordings/start`
    """,
    version=settings.VERSION,
    openapi_tags=OPENAPI_TAGS,
    contact={
        "name": "LiDAR Standalone Team",
    },
    license_info={
        "name": "Proprietary",
    },
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

    # Protected prefixes that should not fall through to SPA
    PROTECTED_PREFIXES = ("/api/", "/recordings/", "/docs", "/redoc", "/openapi.json")

    @app.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            # If the request is not for protected paths, return the SPA index.html
            if not any(request.url.path.startswith(p) for p in PROTECTED_PREFIXES):
                index_path = Path(static_dir) / "index.html"
                if index_path.exists():
                    return FileResponse(index_path)
                    
        # Otherwise, fall back to standard JSON response
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        
else:
    logger.warning(f"Static directory not found at {static_dir}")
