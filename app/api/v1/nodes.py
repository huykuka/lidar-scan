"""Node runtime status endpoint"""
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter

from app.services.lidar.instance import lidar_service
from app.repositories import LidarRepository, FusionRepository

router = APIRouter()


@router.get("/nodes/status")
async def get_nodes_status():
    """
    Returns runtime status of all configured lidar sensors and fusion nodes.
    
    For each lidar:
    - enabled: whether it's enabled in DB
    - mode: "real" or "sim"
    - topic_prefix: derived websocket topic prefix
    - raw_topic: websocket topic for raw points
    - processed_topic: websocket topic for processed points
    - running: whether the worker process is alive
    - last_frame_at: unix timestamp of last received frame (None if never)
    - last_error: error message if any
    
    For each fusion:
    - enabled: whether it's enabled
    - topic: websocket topic
    - running: whether fusion is enabled/active
    - last_broadcast_at: unix timestamp of last broadcast (None if never)
    - last_error: error message if any
    """
    
    lidar_repo = LidarRepository()
    fusion_repo = FusionRepository()
    
    # Get DB configs to include disabled nodes
    lidar_configs = lidar_repo.list()
    fusion_configs = fusion_repo.list()
    
    # Build lidar status
    lidars_status: List[Dict[str, Any]] = []
    for config in lidar_configs:
        sensor_id = config["id"]
        enabled = bool(config.get("enabled", True))
        
        # Find runtime data if sensor is running
        runtime = lidar_service.lidar_runtime.get(sensor_id, {})
        process = lidar_service.processes.get(sensor_id)
        
        # Check if process is alive
        process_alive = False
        if process and process.is_alive():
            process_alive = True
        
        # Find the sensor object to get topic_prefix
        sensor = next((s for s in lidar_service.sensors if s.id == sensor_id), None)
        topic_prefix = sensor.topic_prefix if sensor else config.get("topic_prefix", sensor_id)
        
        last_frame_at = runtime.get("last_frame_at")
        last_error = runtime.get("last_error")
        mode = config.get("mode", "real")
        
        # Calculate frame age if we have a timestamp
        frame_age_seconds: Optional[float] = None
        if last_frame_at:
            frame_age_seconds = time.time() - last_frame_at
        
        lidars_status.append({
            "id": sensor_id,
            "name": config.get("name", sensor_id),
            "enabled": enabled,
            "mode": mode,
            "topic_prefix": topic_prefix,
            "raw_topic": f"{topic_prefix}_raw_points",
            "processed_topic": f"{topic_prefix}_processed_points" if config.get("pipeline_name") else None,
            "running": process_alive and enabled,
            "last_frame_at": last_frame_at,
            "frame_age_seconds": frame_age_seconds,
            "last_error": last_error,
        })
    
    # Build fusion status
    fusions_status: List[Dict[str, Any]] = []
    for config in fusion_configs:
        fusion_id = config["id"]
        enabled = bool(config.get("enabled", True))
        
        # Find the fusion service object
        fusion = next((f for f in lidar_service.fusions if getattr(f, "id", None) == fusion_id), None)
        
        running = False
        last_broadcast_at = None
        last_error = None
        broadcast_age_seconds: Optional[float] = None
        
        if fusion:
            running = fusion.enabled and enabled
            last_broadcast_at = getattr(fusion, "last_broadcast_at", None)
            last_error = getattr(fusion, "last_error", None)
            
            if last_broadcast_at:
                broadcast_age_seconds = time.time() - last_broadcast_at
        
        fusions_status.append({
            "id": fusion_id,
            "topic": config.get("topic", "fused_points"),
            "sensor_ids": config.get("sensor_ids", []),
            "enabled": enabled,
            "running": running,
            "last_broadcast_at": last_broadcast_at,
            "broadcast_age_seconds": broadcast_age_seconds,
            "last_error": last_error,
        })
    
    return {
        "lidars": lidars_status,
        "fusions": fusions_status,
    }
