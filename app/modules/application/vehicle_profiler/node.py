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
    - Partial profiles (``stream_partial=True``) are forwarded through
      ``manager.forward_data`` with ``metadata.partial=True`` so the node
      manager handles all WS broadcasting — no direct ws_manager calls here.
"""
import asyncio
import enum
import time
from typing import Any, Dict, List, Optional, Set

import numpy as np

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.shared.binary import pack_points_binary
from app.services.status_aggregator import notify_status_change
from app.services.websocket.manager import manager as ws_manager

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
        self._ws_topic: Optional[str] = None  # set by orchestrator on registration

        self._velocity_sensor_id = velocity_sensor_id

        # Vehicle detector params
        travel_axis = int(config.get("travel_axis", 0))
        max_correspondence_distance = float(config.get("max_correspondence_distance", 0.5))
        min_icp_fitness = float(config.get("min_icp_fitness", 0.3))
        max_displacement = float(config.get("max_displacement", 0.5))
        min_displacement = float(config.get("min_displacement", 0.001))

        _min_vehicle_points = int(config.get("min_vehicle_points", 10))
        _dbscan_eps = float(config.get("dbscan_eps", 0.3))
        _dbscan_min_samples = int(config.get("dbscan_min_samples", 5))
        _voxel_size = float(config.get("voxel_size", 0.0))

        trigger_distance_raw = config.get("trigger_distance")
        trigger_distance = float(trigger_distance_raw) if trigger_distance_raw not in (None, "") else None

        self._detector = VehicleDetector(
            travel_axis=travel_axis,
            min_vehicle_points=_min_vehicle_points,
            dbscan_eps=_dbscan_eps,
            dbscan_min_samples=_dbscan_min_samples,
            trigger_distance=trigger_distance,
            max_correspondence_distance=max_correspondence_distance,
            min_icp_fitness=min_icp_fitness,
            voxel_size=_voxel_size,
            max_displacement=max_displacement,
            min_displacement=min_displacement,
        )

        # Profile accumulator params
        min_scan_lines = int(config.get("min_scan_lines", 20))
        min_height = float(config.get("min_height", 0.0))

        self._profiler = ProfileAccumulator(
            min_scan_lines=min_scan_lines,
            travel_axis=travel_axis,
            min_position_delta=min_displacement,
            min_height=min_height,
        )

        # Minimum velocity gate — profile frames are discarded when the
        # detector's estimated velocity is below this threshold (m/s).
        self._min_velocity: float = float(config.get("min_velocity", 0.0))

        # State machine
        self._state = _State.IDLE
        self._vehicles_counted: int = 0

        # Runtime stats
        self.last_input_at: Optional[float] = None
        self.last_output_at: Optional[float] = None
        self.last_error: Optional[str] = None

        self.last_profile_points: int = 0

        # Processing guards — prevent concurrent processing of same sensor type
        self._velocity_processing: bool = False
        self._profile_processing: bool = False

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
            is_positioning_sensor = (
                source_id == self._velocity_sensor_id
                or payload.get("node_id") == self._velocity_sensor_id
                or payload.get("lidar_id") == self._velocity_sensor_id
            )
            if is_positioning_sensor:
                await self._handle_velocity_frame(points, timestamp)
            else:
                await self._handle_profile_frame(source_id, points, timestamp)
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

        logger.debug(
            "[%s] detector: present=%s pos=%.3f vel=%.3f icp=%s state=%s",
            self.id, result.vehicle_present, result.position,
            result.velocity, result.icp_valid, self._state.value,
        )

        if result.vehicle_present and self._state == _State.IDLE:
            self._state = _State.MEASURING
            self._profiler.start_vehicle()
            logger.info(f"[{self.id}] Vehicle detected — starting profile capture")
            notify_status_change(self.id)

        elif not result.vehicle_present and self._state == _State.MEASURING:
            logger.info(f"[{self.id}] Vehicle departed — finalizing profile")
            await self._finalize_profile()

    async def _handle_profile_frame(
        self, sensor_id: str, points: np.ndarray, timestamp: float
    ) -> None:
        if self._state != _State.MEASURING:
            return

        # Gate on minimum velocity — skip scan lines when vehicle is too slow
        # (e.g. stationary or reversing).  Strict inequality so that
        # min_velocity=0.0 (default) accepts zero-velocity frames.
        if self._detector.current_velocity < self._min_velocity:
            return

        position = self._detector.get_position_at(timestamp)
        if position is None:
            return  # timestamp too far from any velocity sample — skip this line
        self._profiler.add_scan_line(sensor_id, points, position, timestamp)

        # Stream partial profile directly to WebSocket for real-time visualization only
        # NOT forwarded to downstream DAG nodes — only the final complete profile is forwarded on vehicle departure
        accumulated = self._profiler.get_accumulated_cloud()
        if accumulated is not None:
            self.last_output_at = time.time()
            self.last_profile_points = len(accumulated)
            asyncio.create_task(self._broadcast_ws(accumulated, timestamp))

    async def _broadcast_ws(self, points: np.ndarray, timestamp: float) -> None:
        """Broadcast point cloud to WebSocket subscribers (LIDR binary).

        Only streams XYZ for visualization.  Does NOT forward to downstream
        DAG nodes — that is exclusively done by ``_finalize_profile``.
        """
        topic = self._ws_topic
        if not topic or not ws_manager.has_subscribers(topic):
            return
        try:
            binary = await asyncio.to_thread(pack_points_binary, points, timestamp)
            await ws_manager.broadcast(topic, binary)
        except Exception as e:
            logger.warning(f"[{self.id}] WS broadcast failed: {e}")

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
