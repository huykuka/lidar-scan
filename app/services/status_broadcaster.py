"""Background service that broadcasts node status updates via WebSocket."""
import asyncio
import time
from typing import Any, Dict, List, Optional

from app.services.websocket.manager import manager
from app.services.lidar.instance import lidar_service
from app.repositories import LidarRepository, FusionRepository

_broadcast_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def _build_status_message() -> Dict[str, Any]:
    """Build the status message payload (same format as GET /nodes/status)."""
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
        connection_status = runtime.get("connection_status", "unknown")
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
            "connection_status": connection_status,
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


async def _status_broadcast_loop():
    """Background loop that broadcasts status every 2 seconds."""
    global _stop_event
    
    # Register the status topic
    manager.register_topic("system_status")
    
    while not _stop_event.is_set():
        try:
            # Build status payload
            status = _build_status_message()
            
            # Broadcast to all connected clients
            await manager.broadcast("system_status", status)
            
        except Exception as e:
            print(f"[StatusBroadcaster] Error broadcasting status: {e}")
        
        # Wait 2 seconds before next broadcast
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=2.0)
            break  # Stop event was set
        except asyncio.TimeoutError:
            continue  # Timeout is normal, continue loop


def start_status_broadcaster():
    """Start the background status broadcaster task."""
    global _broadcast_task, _stop_event
    
    if _broadcast_task is not None:
        return  # Already running
    
    _stop_event = asyncio.Event()
    _broadcast_task = asyncio.create_task(_status_broadcast_loop())
    print("[StatusBroadcaster] Started")


def stop_status_broadcaster():
    """Stop the background status broadcaster task."""
    global _broadcast_task, _stop_event
    
    if _broadcast_task is None:
        return
    
    _stop_event.set()
    _broadcast_task.cancel()
    _broadcast_task = None
    _stop_event = None
    print("[StatusBroadcaster] Stopped")
