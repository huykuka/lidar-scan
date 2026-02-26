import multiprocessing as mp
import time
from typing import Any, Dict
import numpy as np
import open3d as o3d  # type: ignore
from app.core.logging_config import get_logger
from app.services.modules.pipeline.base import PointConverter

logger = get_logger(__name__)

def pcd_worker_process(lidar_id: str, pcd_path: str, data_queue: mp.Queue, stop_event: mp.Event):
    """
    Worker process that simulates a LIDAR by playing back a PCD file.
    Preserves all attributes (intensity, reflector, etc.) if present in the file.
    """
    logger.info(f"[{lidar_id}] PCD Worker starting with file: {pcd_path}")
    
    try:
        # 1. Use Tensor-based IO to preserve all attributes
        t_pcd = o3d.t.io.read_point_cloud(pcd_path)
        if t_pcd.is_empty():
            logger.error(f"[{lidar_id}] Error: PCD file is empty or could not be loaded: {pcd_path}")
            return
            
            
        # 2. Convert to our standard (N, 14) numpy format for the graph
        points = PointConverter.to_points(t_pcd)
        logger.info(f"[{lidar_id}] Loaded {len(points)} points from {pcd_path} with {points.shape[1]} channels")
        
    except Exception as e:
        logger.error(f"[{lidar_id}] Error loading PCD file: {e}", exc_info=True)
        return

    # Simulation loop
    while not stop_event.is_set():
        start_time = time.time()
        timestamp = start_time
        
        # Simulate 10Hz
        points_copy = points.copy()
        
        payload = {
            "lidar_id": lidar_id,
            "processed": False,
            "points": points_copy,
            "count": len(points_copy),
            "timestamp": timestamp
        }
        
        try:
            data_queue.put(payload, block=False)
        except Exception:
            pass  # Queue full or closed

        # Sleep to maintain approx 10Hz
        elapsed = time.time() - start_time
        sleep_time = max(0.0, 0.04 - elapsed)
        time.sleep(sleep_time)

    logger.info(f"[{lidar_id}] PCD Worker stopped.")
