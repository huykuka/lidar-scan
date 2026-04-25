"""
LiDAR sensor model representing configuration and state.
"""
from typing import Dict, Optional, Any
import asyncio
import multiprocessing as mp
import time

import numpy as np

from app.core.logging import get_logger
from app.modules.lidar.core import create_transformation_matrix, pose_to_dict
from app.schemas.pose import Pose
from app.services.nodes.base_module import ModuleNode
from app.schemas.status import NodeStatusUpdate, OperationalState, ApplicationState
from app.services.status_aggregator import notify_status_change

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
        transformation: Optional[np.ndarray] = None,
        name: Optional[str] = None,
        topic_prefix: Optional[str] = None,
        throttle_ms: float = 0
    ):
        self.manager = manager
        self.id = sensor_id
        self.name = name or sensor_id
        self.topic_prefix = topic_prefix or self.name
        self.launch_args = launch_args
        
        # LiDAR model information (set externally by build_sensor after instantiation)
        self.lidar_type: str = "multiscan"
        self.lidar_display_name: str = "SICK multiScan"
        
        self.transformation = transformation if transformation is not None else np.eye(4)
        self.pose_params: Pose = Pose.zero()
        
        self._process = None
        self._stop_event = None

    def set_pose(self, pose: Pose) -> "LidarSensor":
        """Set the sensor pose and recompute the transformation matrix.

        Args:
            pose: Canonical 6-DOF Pose instance.

        Returns:
            self — to allow method chaining.
        """
        self.transformation = create_transformation_matrix(**pose.to_flat_dict())
        self.pose_params = pose
        return self

    def get_pose_params(self) -> Pose:
        """Return the current sensor pose as a Pose instance."""
        return self.pose_params

    async def on_input(self, payload: Dict[str, Any]):
        """Standard ModuleNode interface - delegates to handle_data"""
        # LidarSensor is a source node, so it doesn't receive input from upstream.
        # This method exists to satisfy the ModuleNode interface.
        pass

    def start(self, data_queue: Optional[mp.Queue] = None, runtime_status: Optional[Dict[str, Any]] = None):
        """Starts the worker process for this sensor"""
        if data_queue is None or runtime_status is None:
            raise ValueError("LidarSensor requires data_queue and runtime_status")
        
        # Check if process is already running
        if self._process and self._process.is_alive():
            logger.warning(f"[{self.id}] Worker process already running (PID: {self._process.pid}), skipping start")
            return
        
        self._stop_event = mp.Event()
        
        runtime_status[self.id] = {
            "last_frame_at": None,
            "last_error": None,
            "process_alive": False,
            "connection_status": "starting",
        }
        
        try:
            from app.modules.lidar.workers.real import lidar_worker_process
            self._process = mp.Process(
                target=lidar_worker_process,
                args=(self.id, self.launch_args, data_queue, self._stop_event),
                name=f"LidarWorker-{self.id}",
                daemon=True
            )
            
            self._process.start()
            runtime_status[self.id]["process_alive"] = True
            logger.info(f"Spawned worker for {self.id} (PID: {self._process.pid})")
            
            # Notify status change after starting
            notify_status_change(self.id)
        except Exception as e:
            error_msg = f"Failed to start worker: {e}"
            logger.error(f"[{self.id}] {error_msg}", exc_info=True)
            runtime_status[self.id]["last_error"] = error_msg
            notify_status_change(self.id)

    def stop(self):
        """Stops the worker process for this sensor"""
        if self._stop_event:
            self._stop_event.set()
        
        if self._process and self._process.is_alive():
            logger.info(f"[{self.id}] Stopping worker process (PID: {self._process.pid})...")
            
            # Give the process time to finish gracefully
            self._process.join(timeout=2.0)
            
            if self._process.is_alive():
                logger.warning(f"[{self.id}] Worker didn't stop gracefully, terminating...")
                self._process.terminate()
                self._process.join(timeout=1.0)
                
                if self._process.is_alive():
                    logger.error(f"[{self.id}] Worker still alive after terminate, killing...")
                    self._process.kill()
                    self._process.join(timeout=0.5)
        
        self._process = None
        self._stop_event = None
        logger.info(f"[{self.id}] Worker process stopped.")
        
        # Notify status change after stopping
        notify_status_change(self.id)

    async def handle_data(self, payload: Dict[str, Any], runtime_status: Dict[str, Any]):
        """Handles incoming data explicitly for this Lidar node"""
        from .core.transformations import transform_points
        
        try:
            timestamp = payload["timestamp"]
            event_type = payload.get("event_type")
            
            if event_type:
                if self.id in runtime_status:
                    if event_type == "connected":
                        runtime_status[self.id]["last_error"] = None
                        runtime_status[self.id]["connection_status"] = "connected"
                        logger.info(f"[{self.id}] Connected: {payload.get('message', '')}")
                        notify_status_change(self.id)
                    elif event_type == "disconnected":
                        runtime_status[self.id]["last_error"] = f"Disconnected: {payload.get('message', 'Connection lost')}"
                        runtime_status[self.id]["connection_status"] = "disconnected"
                        logger.warning(f"[{self.id}] Disconnected: {payload.get('message', '')}")
                        notify_status_change(self.id)
                    elif event_type == "error":
                        runtime_status[self.id]["last_error"] = payload.get("message", "Unknown error")
                        runtime_status[self.id]["connection_status"] = "error"
                        logger.error(f"[{self.id}] Error: {payload.get('message', '')}")
                        notify_status_change(self.id)
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
                transformed_points = await asyncio.to_thread(transform_points, points, self.transformation)
                # Update payload for downstream
                payload["points"] = transformed_points

                frame_count = runtime_status.get(self.id, {}).get("frame_count", 0)
                if frame_count % 100 == 1:
                    logger.debug(f"[{self.id}] Frame #{frame_count}: {len(transformed_points)} points after transform")

                # 2. Forward to downstream nodes via Manager (fire-and-forget)
                # NodeManager will handle WebSocket broadcasting automatically.
                # We don't await here — decouples this sensor from downstream
                # processing latency so slow nodes (e.g. densify) can't stall
                # the producer or starve the event loop.
                asyncio.create_task(self.manager.forward_data(self.id, payload))

        except Exception as e:
            logger.error(f"Error handling data for {self.id}: {e}", exc_info=True)
            if self.id in runtime_status:
                runtime_status[self.id]["last_error"] = str(e)

    def emit_status(self) -> NodeStatusUpdate:
        """Return standardized status for this sensor node.
        
        Maps sensor lifecycle and connection state to OperationalState:
        - Process not alive → STOPPED
        - Process starting up → INITIALIZE
        - Connected and receiving frames → RUNNING
        - Connection error with last_error set → ERROR
        
        Returns:
            NodeStatusUpdate with operational_state and connection_status application_state
        """
        # Read runtime status from manager
        runtime_status = getattr(self.manager, 'node_runtime_status', {})
        runtime = runtime_status.get(self.id, {})
        
        connection_status = runtime.get("connection_status", "disconnected")
        last_error = runtime.get("last_error")
        process_alive = self._process.is_alive() if self._process else False
        
        # Determine operational state
        if not process_alive:
            operational_state = OperationalState.STOPPED
            app_value = "disconnected"
            app_color = "red"
        elif last_error:
            # Error state - process alive but connection failed
            operational_state = OperationalState.ERROR
            app_value = "disconnected"
            app_color = "red"
        elif connection_status == "starting":
            operational_state = OperationalState.INITIALIZE
            app_value = "starting"
            app_color = "orange"
        elif connection_status == "connected":
            operational_state = OperationalState.RUNNING
            app_value = "connected"
            app_color = "green"
        else:
            # Fallback: process alive but not connected yet
            operational_state = OperationalState.STOPPED
            app_value = "disconnected"
            app_color = "red"
        
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=operational_state,
            application_state=ApplicationState(
                label="connection_status",
                value=app_value,
                color=app_color,
            ),
            error_message=last_error,
        )
