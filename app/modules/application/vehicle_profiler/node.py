"""
VehicleProfilerNode — Application-level DAG node for multi-2D-LiDAR vehicle
velocity measurement and side-profile reconstruction.

DAG wiring:
    [LiDAR Sensor A (vertical)] ──┐
    [LiDAR Sensor B (side)]     ──┼──► [Vehicle Profiler] ──► profile cloud
    [LiDAR Sensor C (side)]     ──┘

State machine:
    IDLE ──(vehicle detected)──► MEASURING ──(vehicle left)──► IDLE
                                     │
                               (emit profile)

Architecture:
    - ``on_input`` dispatches each frame to either the velocity estimator or
      the profile accumulator based on the source sensor ID.
    - Heavy processing runs in ``asyncio.to_thread()`` to avoid blocking
      the FastAPI event loop.
"""
import asyncio
import enum
import time
from typing import Any, Dict, List, Optional, Set

import numpy as np

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change

from .utils.detector import VehicleDetector
from .utils.profiler import ProfileAccumulator

logger = get_logger(__name__)


class _State(enum.Enum):
    IDLE = "idle"
    MEASURING = "measuring"


class VehicleProfilerNode(ModuleNode):
    """Multi-2D-LiDAR node: one vertical sensor for velocity, N side sensors
    for profile reconstruction.

    Args:
        manager:             NodeManager reference.
        node_id:             Unique node ID.
        name:                Display name.
        velocity_sensor_id:  Node ID of the vertical (velocity) LiDAR.
        config:              Node configuration dict (from registry properties).
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        velocity_sensor_id: str,
        config: Dict[str, Any],
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name

        self._velocity_sensor_id = velocity_sensor_id

        # Vehicle detector params
        bg_threshold = float(config.get("bg_threshold", 0.3))
        bg_learning_frames = int(config.get("bg_learning_frames", 20))
        travel_axis = int(config.get("travel_axis", 0))
        min_vehicle_points = int(config.get("min_vehicle_points", 5))
        max_correspondence_distance = float(config.get("max_correspondence_distance", 0.5))
        min_icp_fitness = float(config.get("min_icp_fitness", 0.3))
        voxel_size = float(config.get("voxel_size", 0.0))
        max_displacement = float(config.get("max_displacement", 0.5))
        min_displacement = float(config.get("min_displacement", 0.005))
        gap_debounce_s = float(config.get("gap_debounce_s", 3.0))

        self._detector = VehicleDetector(
            bg_threshold=bg_threshold,
            bg_learning_frames=bg_learning_frames,
            travel_axis=travel_axis,
            gap_debounce_s=gap_debounce_s,
            min_vehicle_points=min_vehicle_points,
            max_correspondence_distance=max_correspondence_distance,
            min_icp_fitness=min_icp_fitness,
            voxel_size=voxel_size,
            max_displacement=max_displacement,
            min_displacement=min_displacement,
        )

        # Profile accumulator params
        min_scan_lines = int(config.get("min_scan_lines", 10))
        max_gap_s = float(config.get("max_gap_s", 2.0))
        min_position_delta = float(config.get("min_position_delta", 0.0))

        self._profiler = ProfileAccumulator(
            min_scan_lines=min_scan_lines,
            max_gap_s=max_gap_s,
            travel_axis=travel_axis,
            min_position_delta=min_position_delta,
        )

        # Stream partial (accumulated) profile in real-time while measuring.
        self._stream_partial = bool(config.get("stream_partial", False))

        # State machine
        self._state = _State.IDLE
        self._vehicles_counted: int = 0

        # Independent processing guards — velocity (ICP) and profile frames
        # run concurrently so a slow ICP call never drops a profile frame.
        self._velocity_processing: bool = False
        self._profile_processing: bool = False

        # Runtime stats
        self.last_input_at: Optional[float] = None
        self.last_output_at: Optional[float] = None
        self.last_error: Optional[str] = None

        self.last_profile_points: int = 0

    # ── ModuleNode interface ──────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        source_id = payload.get("lidar_id") or payload.get("node_id")
        if not source_id:
            return

        points = payload.get("points")
        if points is None or len(points) == 0:
            return

        timestamp = payload.get("timestamp", time.time())
        self.last_input_at = time.time()

        try:
            # Match velocity sensor by either lidar_id or node_id so that
            # auto-detect (which picks from edge source_node) works even
            # when the payload carries a different lidar_id through
            # intermediate DAG nodes (e.g. Sensor → Crop → Profiler).
            is_velocity = (
                source_id == self._velocity_sensor_id
                or payload.get("node_id") == self._velocity_sensor_id
                or payload.get("lidar_id") == self._velocity_sensor_id
            )
            if is_velocity:
                if self._velocity_processing:
                    logger.debug(f"[{self.id}] Dropping velocity frame — ICP still running")
                    return
                self._velocity_processing = True
                try:
                    await self._handle_velocity_frame(points, timestamp)
                finally:
                    self._velocity_processing = False
            else:
                if self._profile_processing:
                    logger.debug(f"[{self.id}] Dropping profile frame — previous profile frame still processing")
                    return
                self._profile_processing = True
                try:
                    await self._handle_profile_frame(source_id, points, timestamp)
                finally:
                    self._profile_processing = False
            self.last_error = None
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"[{self.id}] Error processing frame from {source_id}: {e}", exc_info=True)
            notify_status_change(self.id)

    def emit_status(self) -> NodeStatusUpdate:
        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(
                    label="state",
                    value=self._state.value,
                    color="red",
                ),
                error_message=self.last_error,
            )

        color_map = {
            _State.IDLE: "gray",
            _State.MEASURING: "blue",
        }
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="state",
                value=self._state.value,
                color=color_map.get(self._state, "gray"),
            ),
        )

    def start(self, data_queue: Any = None, runtime_status: Any = None) -> None:
        notify_status_change(self.id)

    def stop(self) -> None:
        self._transition_to_idle()

    # ── Internal handlers ─────────────────────────────────────────────────

    async def _handle_velocity_frame(self, points: np.ndarray, timestamp: float) -> None:
        result = await asyncio.to_thread(self._detector.update, points, timestamp)

        if result is None:
            return
        if result.vehicle_present and self._state == _State.IDLE:
            self._state = _State.MEASURING
            self._profiler.start_vehicle()
            logger.info(f"[{self.id}] Vehicle detected — starting profile capture")
            notify_status_change(self.id)

        elif not result.vehicle_present and self._state == _State.MEASURING:
            await self._finalize_profile()

    async def _handle_profile_frame(
        self, sensor_id: str, points: np.ndarray, timestamp: float
    ) -> None:
        if self._state != _State.MEASURING:
            return

        position = self._detector.current_position

        self._profiler.add_scan_line(sensor_id, points, position, timestamp)

        if not self._stream_partial:
            return

        # Stream the accumulated partial profile so the UI can show
        # the point cloud building up in real-time.
        accumulated = self._profiler.get_accumulated_cloud()
        if accumulated is not None:
            self.last_output_at = time.time()
            self.last_profile_points = len(accumulated)
            partial_payload = {
                "node_id": self.id,
                "points": accumulated,
                "timestamp": timestamp,
                "count": len(accumulated),
                "metadata": {
                    "partial": True,
                    "scan_count": self._profiler.scan_count,
                },
            }
            asyncio.create_task(self.manager.forward_data(self.id, partial_payload))

    async def _finalize_profile(self) -> None:
        profile = await asyncio.to_thread(self._profiler.finish_vehicle)

        if profile is not None and len(profile.points) > 0:
            self._vehicles_counted += 1
            self.last_output_at = time.time()
            self.last_profile_points = len(profile.points)

            logger.info(
                f"[{self.id}] Vehicle #{self._vehicles_counted} profile complete: "
                f"{len(profile.points)} pts, {profile.scan_count} scans, "
                f"est_length={profile.estimated_length:.3f} m, "
                f"duration={profile.duration:.2f} s"
            )

            out_payload = {
                "node_id": self.id,
                "points": profile.points,
                "timestamp": profile.end_time,
                "count": len(profile.points),
                "metadata": {
                    "partial": False,
                    "vehicle_number": self._vehicles_counted,
                    "scan_count": profile.scan_count,
                    "estimated_length": profile.estimated_length,
                    "duration": profile.duration,
                    "sensor_ids": profile.sensor_ids,
                },
            }
            asyncio.create_task(self.manager.forward_data(self.id, out_payload))
        else:
            logger.debug(f"[{self.id}] Vehicle left but profile had too few scan lines — discarded")

        self._transition_to_idle()

    def _transition_to_idle(self) -> None:
        self._state = _State.IDLE
        self._profiler.abort()
        self._detector.reset_tracking()
        self.last_error = None
        notify_status_change(self.id)
