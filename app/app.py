from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import asyncio
import os
from app.api.v1.endpoints import router as api_router
from app.services.lidar.service import LidarService, LidarSensor
from app.pipeline import PipelineFactory
from app.core.config import settings

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

# Mount static files
app.mount("/static", StaticFiles(directory="app/static", html=True), name="static")

@app.get("/")
async def read_index():
    from fastapi.responses import FileResponse
    return FileResponse("app/static/index.html")

# Central Service
lidar_service = LidarService()

@app.on_event("startup")
async def startup_event():
    # 1. Setup Sensors
    launch_file = settings.LIDAR_LAUNCH
    hostname = settings.LIDAR_IP
    lidar_mode = settings.LIDAR_MODE
    pcd_path = settings.LIDAR_PCD_PATH

    sensor_id = "front_lidar"
    front_pipeline = PipelineFactory.get("advanced", lidar_id=sensor_id)

    lidar_service.add_sensor(LidarSensor(
        sensor_id=sensor_id,
        launch_args=f"{launch_file} hostname:={hostname}",
        pipeline=front_pipeline,
        mode=lidar_mode,
        pcd_path=pcd_path
    ))

    # 3. Start everything
    lidar_service.start(asyncio.get_running_loop())

    # Example: Sensor 1 with Object Clustering (in parallel)
    # lidar_service.add_sensor(LidarSensor(
    #     sensor_id="back_lidar",
    #     launch_args=f"./launch/sick_tim.launch hostname:=192.168.100.124",
    #     pipeline=object_pipeline
    # ))


@app.on_event("shutdown")
def shutdown_event():
    lidar_service.stop()

@app.get("/status")
async def get_status():
    return {
        "is_running": lidar_service.is_running,
        "active_sensors": [s.id for s in lidar_service.sensors],
        "version": settings.VERSION
    }
