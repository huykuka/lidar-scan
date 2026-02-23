import multiprocessing as mp
import time
from typing import Any
import numpy as np
import open3d as o3d  # type: ignore
from app.core.logging_config import get_logger

logger = get_logger(__name__)

def pcd_worker_process(lidar_id: str, pcd_path: str, pipeline: Any, data_queue: mp.Queue, stop_event: mp.Event):
    """
    Worker process that simulates a LIDAR by playing back a PCD file.
    """
    logger.info(f"[{lidar_id}] PCD Worker starting with file: {pcd_path}")
    try:
        pcd = o3d.io.read_point_cloud(pcd_path)
        if pcd.is_empty():
            logger.error(f"[{lidar_id}] Error: PCD file is empty or could not be loaded: {pcd_path}")
            return
        points = np.asarray(pcd.points, dtype=np.float32)
        logger.info(f"[{lidar_id}] Loaded {len(points)} points from {pcd_path}")
    except Exception as e:
        logger.error(f"[{lidar_id}] Error loading PCD file: {e}", exc_info=True)
        return
    # Simulation loop
    while not stop_event.is_set():
        start_time = time.time()
        timestamp = start_time
        # Simulate 10Hz
        points_copy = points.copy()  # ...
        if pipeline:
            try:
                processed_result = pipeline.process(points_copy)
                payload = {
                    "lidar_id": lidar_id,
                    "processed": True,
                    "data": processed_result,
                    "raw_points": points_copy,
                    "timestamp": timestamp
                }
            except Exception as e:
                logger.error(f"[{lidar_id}] Pipeline processing error: {e}", exc_info=True)
                payload = None
        else:
            payload = {
                "lidar_id": lidar_id,
                "processed": False,
                "points": points_copy,
                "count": len(points_copy),
                "timestamp": timestamp
            }
        if payload:
            try:
                data_queue.put(payload, block=False)
            except Exception:
                pass  # Queue full or closed
        # Sleep to maintain approx 10Hz
        elapsed = time.time() - start_time
        sleep_time = max(0.0, 0.1 - elapsed)
        time.sleep(sleep_time)
    logger.info(f"[{lidar_id}] PCD Worker stopped.")
