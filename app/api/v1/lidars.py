import os
import tempfile
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse
from typing import Optional
from pydantic import BaseModel
from app.services.lidar.instance import lidar_service
from app.services.websocket.manager import manager
from app.services.lidar.io.pcd import unpack_lidr_binary, save_to_pcd
from app.repositories import LidarRepository

router = APIRouter()
lidar_repo = LidarRepository()

class LidarConfig(BaseModel):
    id: Optional[str] = None
    name: str
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
                "name": getattr(s, 'name', s.id),
                "topic_prefix": getattr(s, 'topic_prefix', s.id),
                "raw_topic": f"{getattr(s, 'topic_prefix', s.id)}_raw_points",
                "processed_topic": (
                    f"{getattr(s, 'topic_prefix', s.id)}_processed_points"
                    if getattr(s, 'pipeline', None) is not None
                    else None
                ),
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
    """Adds or updates a lidar configuration and saves to DB"""
    saved_id = lidar_repo.upsert(config.dict())
    return {"status": "success", "message": f"Lidar saved.", "id": saved_id}

@router.post("/lidars/reload")
async def reload_lidars():
    """Reloads the configuration and restarts all lidar processes"""
    lidar_service.reload_config()
    return {"status": "success", "message": "Configuration reloaded."}

@router.delete("/lidars/{lidar_id}")
async def remove_lidar(lidar_id: str):
    """Removes a lidar configuration and saves to DB"""
    lidar_repo.delete(lidar_id)
    return {"status": "success", "message": f"Lidar {lidar_id} removed. Reload to apply."}

@router.get("/lidars/capture")
async def capture_pcd(topic: str, background_tasks: BackgroundTasks):
    """
    Captures the next available frame from a topic and returns it as a PCD file.
    """
    try:
        # 1. Wait for the next message on this topic
        print(f"[Capture] Waiting for next frame on topic: {topic}")
        data = await manager.wait_for_next(topic, timeout=5.0)
        
        if not isinstance(data, bytes):
            return {"status": "error", "message": f"Topic '{topic}' did not provide binary point cloud data."}

        # 2. Unpack LIDR binary format
        points, timestamp = unpack_lidr_binary(data)
        
        # 3. Save to temporary PCD file
        # We use a temporary file that we'll delete after the response is sent
        fd, tmp_path = tempfile.mkstemp(suffix=".pcd")
        try:
            os.close(fd)
            save_to_pcd(points, tmp_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise e

        # 4. Define cleanup task
        def cleanup_temp_file(path: str):
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"[Capture] Cleaned up temporary file: {path}")
                except Exception as e:
                    print(f"[Capture] Error cleaning up {path}: {e}")

        background_tasks.add_task(cleanup_temp_file, tmp_path)

        # 5. Return FileResponse
        filename = f"capture_{topic}_{int(timestamp)}.pcd"
        return FileResponse(
            path=tmp_path,
            filename=filename,
            media_type="application/octet-stream"
        )

    except Exception as e:
        print(f"[Capture] Error: {e}")
        return {"status": "error", "message": str(e)}
