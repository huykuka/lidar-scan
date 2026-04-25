"""
Visionary 3D camera sensor node.

Follows the same pattern as ``app.modules.lidar.node.LidarSensor``:
- Extends ``ModuleNode`` for DAG integration
- Spawns a multiprocessing worker to acquire frames from SICK Visionary cameras
- Applies 6-DOF pose transformation and forwards to downstream nodes
"""
from typing import Any, Dict, Optional
import asyncio
import multiprocessing as mp
import os
import time

import numpy as np

from app.core.logging import get_logger
from app.modules.lidar.core import create_transformation_matrix, pose_to_dict
from app.schemas.pose import Pose
from app.services.nodes.base_module import ModuleNode
from app.schemas.status import NodeStatusUpdate, OperationalState, ApplicationState
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)


class VisionarySensor(ModuleNode):
    """Represents a single SICK Visionary 3D camera and its processing state."""

    name: str
    topic_prefix: str

    def __init__(
        self,
        manager: Any,
        sensor_id: str,
        camera_ip: str = "192.168.1.10",
        streaming_port: int = 2114,
        protocol: str = "UDP",
        cola_protocol: str = "Cola2",
        control_port: int = 2122,
        is_stereo: bool = False,
        acquisition_method: str = "sdk",
        cti_path: Optional[str] = None,
        name: Optional[str] = None,
        topic_prefix: Optional[str] = None,
        throttle_ms: float = 0,
    ):
        self.manager = manager
        self.id = sensor_id
        self.name = name or sensor_id
        self.topic_prefix = topic_prefix or self.name

        self.camera_ip = camera_ip
        self.streaming_port = streaming_port
        self.protocol = protocol
        self.cola_protocol = cola_protocol
        self.control_port = control_port
        self.is_stereo = is_stereo
        self.acquisition_method = acquisition_method
        self.cti_path = cti_path

        self.camera_model: str = "visionary_t_mini_cx"
        self.camera_display_name: str = "Visionary-T Mini CX (V3S105)"

        self.transformation = np.eye(4)
        self.pose_params: Pose = Pose.zero()

        self._process: Optional[mp.Process] = None
        self._stop_event: Optional[mp.Event] = None

    def set_pose(self, pose: Pose) -> "VisionarySensor":
        """Set the sensor pose and recompute the transformation matrix."""
        self.transformation = create_transformation_matrix(**pose.to_flat_dict())
        self.pose_params = pose
        return self

    def get_pose_params(self) -> Pose:
        """Return the current sensor pose."""
        return self.pose_params

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """Source node — does not receive upstream input."""
        pass

    def start(
        self,
        data_queue: Optional[mp.Queue] = None,
        runtime_status: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Spawn the Visionary worker process."""
        if data_queue is None or runtime_status is None:
            raise ValueError("VisionarySensor requires data_queue and runtime_status")

        if self._process and self._process.is_alive():
            logger.warning(
                f"[{self.id}] Worker already running (PID: {self._process.pid}), skipping start"
            )
            return

        self._stop_event = mp.Event()

        runtime_status[self.id] = {
            "last_frame_at": None,
            "last_error": None,
            "process_alive": False,
            "mode": "real",
            "connection_status": "starting",
        }

        try:
            if self.acquisition_method == "harvester":
                from app.modules.visionary.workers.harvester import harvester_worker_process

                if not self.cti_path:
                    raise ValueError(
                        "cti_path is required for Harvester/GigE Vision cameras (AP models)"
                    )

                self._process = mp.Process(
                    target=harvester_worker_process,
                    args=(
                        self.id,
                        self.cti_path,
                        self.camera_ip,
                        self.is_stereo,
                        data_queue,
                        self._stop_event,
                    ),
                    name=f"VisionaryHarvester-{self.id}",
                    daemon=True,
                )
            else:
                from app.modules.visionary.workers.real import visionary_worker_process

                self._process = mp.Process(
                    target=visionary_worker_process,
                    args=(
                        self.id,
                        self.camera_ip,
                        self.streaming_port,
                        self.protocol,
                        self.cola_protocol,
                        self.control_port,
                        self.is_stereo,
                        data_queue,
                        self._stop_event,
                    ),
                    name=f"VisionaryWorker-{self.id}",
                    daemon=True,
                )
            self._process.start()
            runtime_status[self.id]["process_alive"] = True
            logger.info(f"Spawned visionary worker for {self.id} (PID: {self._process.pid})")
            notify_status_change(self.id)
        except Exception as exc:
            error_msg = f"Failed to start worker: {exc}"
            logger.error(f"[{self.id}] {error_msg}", exc_info=True)
            runtime_status[self.id]["last_error"] = error_msg
            notify_status_change(self.id)

    def stop(self) -> None:
        """Terminate the worker process gracefully."""
        if self._stop_event:
            self._stop_event.set()

        if self._process and self._process.is_alive():
            logger.info(f"[{self.id}] Stopping worker (PID: {self._process.pid})...")
            self._process.join(timeout=2.0)

            if self._process.is_alive():
                logger.warning(f"[{self.id}] Worker didn't stop gracefully, terminating...")
                self._process.terminate()
                self._process.join(timeout=1.0)

                if self._process.is_alive():
                    logger.error(f"[{self.id}] Worker still alive, killing...")
                    self._process.kill()
                    self._process.join(timeout=0.5)

        self._process = None
        self._stop_event = None
        logger.info(f"[{self.id}] Worker stopped.")
        notify_status_change(self.id)

    async def handle_data(
        self, payload: Dict[str, Any], runtime_status: Dict[str, Any]
    ) -> None:
        """Handle incoming frames from the worker process."""
        from app.modules.lidar.core.transformations import transform_points

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
                        runtime_status[self.id]["last_error"] = (
                            f"Disconnected: {payload.get('message', 'Connection lost')}"
                        )
                        runtime_status[self.id]["connection_status"] = "disconnected"
                        logger.warning(f"[{self.id}] Disconnected: {payload.get('message', '')}")
                        notify_status_change(self.id)
                    elif event_type == "error":
                        runtime_status[self.id]["last_error"] = payload.get(
                            "message", "Unknown error"
                        )
                        runtime_status[self.id]["connection_status"] = "error"
                        logger.error(f"[{self.id}] Error: {payload.get('message', '')}")
                        notify_status_change(self.id)
                return

            if self.id in runtime_status:
                runtime_status[self.id]["last_frame_at"] = time.time()
                runtime_status[self.id]["last_error"] = None
                runtime_status[self.id]["connection_status"] = "connected"
                frame_count = runtime_status[self.id].get("frame_count", 0) + 1
                runtime_status[self.id]["frame_count"] = frame_count

            points = payload.get("points")
            if points is not None:
                transformed_points = await asyncio.to_thread(
                    transform_points, points, self.transformation
                )
                payload["points"] = transformed_points

                frame_count = runtime_status.get(self.id, {}).get("frame_count", 0)
                if frame_count % 100 == 1:
                    logger.debug(
                        f"[{self.id}] Frame #{frame_count}: "
                        f"{len(transformed_points)} points after transform"
                    )

                asyncio.create_task(self.manager.forward_data(self.id, payload))

        except Exception as exc:
            logger.error(f"Error handling data for {self.id}: {exc}", exc_info=True)
            if self.id in runtime_status:
                runtime_status[self.id]["last_error"] = str(exc)

    def emit_status(self) -> NodeStatusUpdate:
        """Return standardised status for this Visionary sensor node."""
        runtime_status = getattr(self.manager, "node_runtime_status", {})
        runtime = runtime_status.get(self.id, {})

        connection_status = runtime.get("connection_status", "disconnected")
        last_error = runtime.get("last_error")
        process_alive = self._process.is_alive() if self._process else False

        if not process_alive:
            operational_state = OperationalState.STOPPED
            app_value = "disconnected"
            app_color = "red"
        elif last_error:
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
