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
    name: Optional[str] = None
    topic_prefix: Optional[str] = None
    enabled: Optional[bool] = None
    launch_args: Optional[str] = None
    pipeline_name: Optional[str] = None
    mode: str = "real"
    pcd_path: Optional[str] = None
    x: float = 0
    y: float = 0
    z: float = 0
    roll: float = 0
    pitch: float = 0
    yaw: float = 0
    imu_udp_port: Optional[int] = None

@router.get("/lidars")
async def list_lidars():
    """Returns all registered lidars and available pipelines"""
    lidars = lidar_repo.list()
    return {
        "lidars": [
            {
                "id": s.get("id"),
                "name": s.get("name") or s.get("id"),
                "topic_prefix": s.get("topic_prefix") or (s.get("name") or s.get("id")),
                "raw_topic": f"{(s.get('topic_prefix') or (s.get('name') or s.get('id')))}_raw_points",
                "processed_topic": (
                    f"{(s.get('topic_prefix') or (s.get('name') or s.get('id')))}_processed_points"
                    if s.get("pipeline_name")
                    else None
                ),
                "enabled": bool(s.get("enabled", True)),
                "launch_args": s.get("launch_args"),
                "pipeline_name": s.get("pipeline_name"),
                "mode": s.get("mode", "real"),
                "pcd_path": s.get("pcd_path"),
                "imu_udp_port": s.get("imu_udp_port"),
                "pose": {
                    "x": s.get("x", 0),
                    "y": s.get("y", 0),
                    "z": s.get("z", 0),
                    "roll": s.get("roll", 0),
                    "pitch": s.get("pitch", 0),
                    "yaw": s.get("yaw", 0),
                },
            }
            for s in lidars
        ],
        "available_pipelines": lidar_service.get_pipelines()
    }

@router.post("/lidars")
async def create_lidar(config: LidarConfig):
    """Adds or updates a lidar configuration and saves to DB"""
    saved_id = lidar_repo.upsert(config.model_dump())
    return {"status": "success", "message": f"Lidar saved.", "id": saved_id}


@router.post("/lidars/{lidar_id}/enabled")
async def set_lidar_enabled(lidar_id: str, enabled: bool):
    """Enable/disable a lidar node, then reload config."""
    lidar_repo.set_enabled(lidar_id, enabled)
    lidar_service.reload_config()
    return {"status": "success", "id": lidar_id, "enabled": enabled}


@router.post("/lidars/{lidar_id}/topic_prefix")
async def set_lidar_topic_prefix(lidar_id: str, topic_prefix: str):
    """Update topic prefix, then reload config."""
    lidar_repo.upsert({"id": lidar_id, "topic_prefix": topic_prefix})
    lidar_service.reload_config()
    return {"status": "success", "id": lidar_id, "topic_prefix": topic_prefix}

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
