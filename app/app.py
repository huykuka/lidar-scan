from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import router as api_router
from app.core.config import settings
from app.core.lifespan import lifespan
from app.core.openapi import OPENAPI_TAGS

app = FastAPI(
    title="LiDAR Studio API",
    description=(
        "Real-time point-cloud processing pipeline REST interface.\n\n"
        "> Binary streaming is served over the `LIDR` WebSocket protocol.\n\n"
        "**Quick-start:** `GET /api/v1/status` → `GET /api/v1/nodes` → `POST /api/v1/recordings/start`"
    ),
    version=settings.VERSION,
    openapi_tags=OPENAPI_TAGS,
    contact={"name": "LiDAR Studio"},
    license_info={"name": "Proprietary"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Static mounts — created eagerly so the mount never fails on a fresh checkout
for _path, _name in [("data/recordings", "recordings"), ("data", "data")]:
    _dir = Path(_path)
    _dir.mkdir(parents=True, exist_ok=True)
    app.mount(f"/{_path.split('/')[-1]}", StaticFiles(directory=str(_dir)), name=_name)

# Serve the Angular frontend
app.frontend('/', directory="app/static", fallback="index.html")
