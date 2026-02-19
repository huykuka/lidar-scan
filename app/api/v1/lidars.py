from fastapi import APIRouter
from typing import Optional
from pydantic import BaseModel
from app.services.lidar.instance import lidar_service

router = APIRouter()

class LidarConfig(BaseModel):
    id: str
    launch_args: str
    pipeline_name: Optional[str] = None
    mode: str = "real"
    pcd_path: Optional[str] = None
    x: float = 0
    y: float = 0
    z: float = 0
    roll: float = 0
    pitch: float = 0
    yaw: float = 0

@router.get("/lidars")
async def list_lidars():
    """Returns all registered lidars and available pipelines"""
    return {
        "lidars": [
            {
                "id": s.id,
                "launch_args": s.launch_args,
                "pipeline_name": s.pipeline_name,
                "mode": s.mode,
                "pcd_path": s.pcd_path,
                "pose": s.pose_params
            } for s in lidar_service.sensors
        ],
        "available_pipelines": lidar_service.get_pipelines()
    }

@router.post("/lidars")
async def create_lidar(config: LidarConfig):
    """Adds or updates a lidar configuration and saves to JSON"""
    # Remove if exists to update
    lidar_service.sensors = [s for s in lidar_service.sensors if s.id != config.id]
    
    lidar_service.generate_lidar(
        sensor_id=config.id,
        launch_args=config.launch_args,
        pipeline_name=config.pipeline_name,
        mode=config.mode,
        pcd_path=config.pcd_path,
        x=config.x, y=config.y, z=config.z,
        roll=config.roll, pitch=config.pitch, yaw=config.yaw
    )
    lidar_service.save_config()
    return {"status": "success", "message": f"Lidar {config.id} saved. Reload to apply."}

@router.post("/lidars/reload")
async def reload_lidars():
    """Reloads the configuration and restarts all lidar processes"""
    lidar_service.reload_config()
    return {"status": "success", "message": "Configuration reloaded."}

@router.delete("/lidars/{lidar_id}")
async def delete_lidar(lidar_id: str):
    """Removes a lidar configuration and saves to JSON"""
    initial_count = len(lidar_service.sensors)
    lidar_service.sensors = [s for s in lidar_service.sensors if s.id != lidar_id]
    
    if len(lidar_service.sensors) < initial_count:
        lidar_service.save_config()
        return {"status": "success", "message": f"Lidar {lidar_id} removed. Reload to apply."}
    
    return {"status": "error", "message": f"Lidar {lidar_id} not found."}
