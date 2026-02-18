import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.endpoints import router as api_router
from app.core.config import settings
from app.services.lidar.service import LidarService

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
    # --- Sensor Setup ---
    lidar_service.generate_lidar(
        sensor_id='lidar1',
        launch_args="./launch/sick_multiscan.launch hostname:=192.168.1.123 udp_receiver_ip:=192.168.1.16 udp_port:=2666",
        pipeline_name="advanced",
    )



    # Example: Sensor 1 with Object Clustering (in parallel)
    # lidar_service.add_sensor(LidarSensor(
    #     sensor_id="back_lidar",
    #     launch_args=f"./launch/sick_tim.launch hostname:=192.168.100.124",
    #     pipeline=object_pipeline
    # ))

    # --- Fusion Examples (uncomment to use) ---
    # from app.services.lidar.fusion import FusionService
    #
    # # Option 1: Fuse ALL registered sensors into a single "fused_points" topic
    # fusion = FusionService(lidar_service)
    # fusion.enable()
    #
    # # Option 2: Fuse only specific sensors (e.g. front + rear, ignoring others)
    # fusion = FusionService(lidar_service, sensor_ids=["lidar_front", "lidar_rear"])
    # fusion.enable()
    #
    # # Option 3: Multiple independent fusion groups on different topics
    # top_fusion    = FusionService(lidar_service, topic="top_fused",    sensor_ids=["lidar_top_left", "lidar_top_right"])
    # ground_fusion = FusionService(lidar_service, topic="ground_fused", sensor_ids=["lidar_front",    "lidar_rear"])
    # top_fusion.enable()
    # ground_fusion.enable()
    #
    # # Option 4: Fuse + run a named pipeline on the merged cloud (same API as generate_lidar)
    # fusion = FusionService(
    #     lidar_service,
    #     topic="fused_reflectors",
    #     sensor_ids=["lidar_front", "lidar_rear"],
    #     pipeline_name="reflector",
    # )
    # fusion.enable()
    

    lidar_service.start(asyncio.get_running_loop())


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
