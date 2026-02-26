"""
LiDAR sensor model representing configuration and state.
"""
from typing import Dict, Optional, Any
import multiprocessing as mp
import os
import time

import numpy as np

from app.services.websocket.manager import manager
from app.core.logging_config import get_logger
from app.services.modules.lidar.core import create_transformation_matrix, pose_to_dict
from app.services.nodes.base_module import ModuleNode

logger = get_logger(__name__)

class LidarSensor(ModuleNode):
    """Represents a single Lidar sensor and its processing pipeline configuration"""

    name: str
    topic_prefix: str

    def __init__(
        self,
        manager: Any,
        sensor_id: str,
        launch_args: str,
        mode: str = "real",
        pcd_path: Optional[str] = None,
        transformation: Optional[np.ndarray] = None,
        name: Optional[str] = None,
        topic_prefix: Optional[str] = None
    ):
        self.manager = manager
        self.id = sensor_id
        self.name = name or sensor_id
        self.topic_prefix = topic_prefix or self.name
        self.launch_args = launch_args
        self.mode = mode
        self.pcd_path = pcd_path
        
        self.transformation = transformation if transformation is not None else np.eye(4)
        self.pose_params: Dict[str, float] = {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        
        self._process = None
        self._stop_event = None

    def set_pose(self, x: float, y: float, z: float, roll: float = 0, pitch: float = 0, yaw: float = 0) -> "LidarSensor":
        self.transformation = create_transformation_matrix(x, y, z, roll, pitch, yaw)
        self.pose_params = pose_to_dict(x, y, z, roll, pitch, yaw)
        return self

    def get_pose_params(self) -> Dict[str, float]:
        return self.pose_params.copy()

    async def on_input(self, payload: Dict[str, Any]):
        """Standard ModuleNode interface - delegates to handle_data"""
        # LidarSensor is a source node, so it doesn't receive input from upstream.
        # This method exists to satisfy the ModuleNode interface.
        pass

    def start(self, data_queue: Optional[mp.Queue] = None, runtime_status: Optional[Dict[str, Any]] = None):
        """Starts the worker process for this sensor"""
        if data_queue is None or runtime_status is None:
            raise ValueError("LidarSensor requires data_queue and runtime_status")
        self._stop_event = mp.Event()
        
        runtime_status[self.id] = {
            "last_frame_at": None,
            "last_error": None,
            "process_alive": False,
            "mode": self.mode,
            "connection_status": "starting",
        }
        
        try:
            if self.mode == "sim":
                if not self.pcd_path or not os.path.exists(self.pcd_path):
                    error_msg = f"PCD file not found: {self.pcd_path or '(not specified)'}"
                    logger.error(f"[{self.id}] {error_msg}")
                    runtime_status[self.id]["last_error"] = error_msg
                    return
                try:
                    from app.services.modules.lidar.workers.pcd import pcd_worker_process
                except ImportError as e:
                    error_msg = f"open3d not available: {e}"
                    logger.error(f"[{self.id}] {error_msg}", exc_info=True)
                    runtime_status[self.id]["last_error"] = error_msg
                    return
                
                self._process = mp.Process(
                    target=pcd_worker_process,
                    args=(self.id, self.pcd_path, data_queue, self._stop_event),
                    name=f"PcdWorker-{self.id}",
                    daemon=True
                )
            else:
                from app.services.modules.lidar.workers.real import lidar_worker_process
                self._process = mp.Process(
                    target=lidar_worker_process,
                    args=(self.id, self.launch_args, data_queue, self._stop_event),
                    name=f"LidarWorker-{self.id}",
                    daemon=True
                )
            
            self._process.start()
            runtime_status[self.id]["process_alive"] = True
            logger.info(f"Spawned worker for {self.id} (PID: {self._process.pid})")
        except Exception as e:
            error_msg = f"Failed to start worker: {e}"
            logger.error(f"[{self.id}] {error_msg}", exc_info=True)
            runtime_status[self.id]["last_error"] = error_msg

    def stop(self):
        """Stops the worker process for this sensor"""
        if self._stop_event:
            self._stop_event.set()
        if self._process:
            self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.terminate()

    async def handle_data(self, payload: Dict[str, Any], runtime_status: Dict[str, Any]):
        """Handles incoming data explicitly for this Lidar node"""
        from .core.transformations import transform_points
        from app.services.shared.binary import pack_points_binary
        
        try:
            timestamp = payload["timestamp"]
            event_type = payload.get("event_type")
            
            if event_type:
                if self.id in runtime_status:
                    if event_type == "connected":
                        runtime_status[self.id]["last_error"] = None
                        runtime_status[self.id]["connection_status"] = "connected"
                        logger.info(f"[{self.id}] Connected: {payload.get('message', '')}")
                    elif event_type == "disconnected":
                        runtime_status[self.id]["last_error"] = f"Disconnected: {payload.get('message', 'Connection lost')}"
                        runtime_status[self.id]["connection_status"] = "disconnected"
                        logger.warning(f"[{self.id}] Disconnected: {payload.get('message', '')}")
                    elif event_type == "error":
                        runtime_status[self.id]["last_error"] = payload.get("message", "Unknown error")
                        runtime_status[self.id]["connection_status"] = "error"
                        logger.error(f"[{self.id}] Error: {payload.get('message', '')}")
                return

            if self.id in runtime_status:
                runtime_status[self.id]["last_frame_at"] = time.time()
                runtime_status[self.id]["last_error"] = None
                runtime_status[self.id]["connection_status"] = "connected"
                # Increment frame counter for debug logging
                frame_count = runtime_status[self.id].get("frame_count", 0) + 1
                runtime_status[self.id]["frame_count"] = frame_count

            points = payload.get("points")
            if points is not None:
                # 1. Transform points to world space off the main thread
                import asyncio
                transformed_points = await asyncio.to_thread(transform_points, points, self.transformation)
                # Update payload for downstream
                payload["points"] = transformed_points

                frame_count = runtime_status.get(self.id, {}).get("frame_count", 0)
                if frame_count % 100 == 1:
                    logger.debug(f"[{self.id}] Frame #{frame_count}: {len(transformed_points)} points after transform")

                # 2. Forward to downstream nodes via Manager
                await self.manager.forward_data(self.id, payload)

                # 3. Handle on-demand WebSocket broadcast
                topic = f"{self.topic_prefix}_raw_points"
                if manager.has_subscribers(topic):
                    import asyncio
                    binary_data = await asyncio.to_thread(pack_points_binary, transformed_points, timestamp)
                    await manager.broadcast(topic, binary_data)
                else:
                    if frame_count % 100 == 1:
                        logger.debug(f"[{self.id}] No subscribers on topic '{topic}' — skipping WS broadcast")

        except Exception as e:
            logger.error(f"Error handling data for {self.id}: {e}", exc_info=True)
            if self.id in runtime_status:
                runtime_status[self.id]["last_error"] = str(e)


    def get_status(self, runtime_status: Dict[str, Any]) -> Dict[str, Any]:
        """Returns standard status for this node"""
        runtime = runtime_status.get(self.id, {}).copy()
        last_frame_at = runtime.get("last_frame_at")
        frame_age = time.time() - last_frame_at if last_frame_at else None
        
        status = {
            "id": self.id,
            "name": self.name,
            "type": "sensor",
            "mode": self.mode,
            "topic_prefix": self.topic_prefix,
            "raw_topic": f"{self.topic_prefix}_raw_points",
            "running": (self._process.is_alive() if self._process else False),
            "connection_status": runtime.get("connection_status", "unknown"),
            "last_frame_at": last_frame_at,
            "frame_age_seconds": frame_age,
            "last_error": runtime.get("last_error"),
        }
        return status
