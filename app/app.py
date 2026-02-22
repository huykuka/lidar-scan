import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import router as api_router
from app.core.config import settings
from app.services.lidar.instance import lidar_service

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend with Modular Pipeline Registry",
    version=settings.VERSION
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


# Central Service (imported from instance)


@app.on_event("startup")
async def startup_event():
    # --- Sensor Setup ---

    lidar_service.load_config()
    lidar_service.start(asyncio.get_running_loop())


@app.on_event("shutdown")
def shutdown_event():
    lidar_service.stop()





# Serve Angular SPA (and assets) from app/static at root.
# Keep this mount LAST so API routes (e.g. /lidars, /ws/*, /status) take precedence.
app.mount("/", StaticFiles(directory="app/static", html=True), name="spa")
