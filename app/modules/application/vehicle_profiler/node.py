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

from .profiler import ProfileAccumulator
from .velocity import VelocityEstimator

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

        # Velocity estimator params
        process_noise = float(config.get("process_noise", 0.1))
        measurement_noise = float(config.get("measurement_noise", 0.5))
        bg_threshold = float(config.get("bg_threshold", 0.3))
        bg_learning_frames = int(config.get("bg_learning_frames", 20))
        travel_axis = int(config.get("travel_axis", 0))

        self._velocity = VelocityEstimator(
            process_noise=process_noise,
            measurement_noise=measurement_noise,
            bg_threshold=bg_threshold,
            bg_learning_frames=bg_learning_frames,
            travel_axis=travel_axis,
        )

        # Profile accumulator params
        min_scan_lines = int(config.get("min_scan_lines", 10))
        max_gap_s = float(config.get("max_gap_s", 2.0))

        self._profiler = ProfileAccumulator(
            min_scan_lines=min_scan_lines,
            max_gap_s=max_gap_s,
        )

        # State machine
        self._state = _State.IDLE
        self._vehicles_counted: int = 0

        # Concurrency guard — prevents re-entrant frame processing when
        # asyncio.to_thread yields control back to the event loop.
        self._processing: bool = False

        # Runtime stats
        self.last_input_at: Optional[float] = None
        self.last_output_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.last_velocity: float = 0.0
        self.last_profile_points: int = 0

    # ── ModuleNode interface ──────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        source_id = payload.get("lidar_id") or payload.get("node_id")
        if not source_id:
            return

        points = payload.get("points")
        if points is None or len(points) == 0:
            return

        if self._processing:
            logger.debug(f"[{self.id}] Dropping frame — node is still processing previous frame")
            return

        timestamp = payload.get("timestamp", time.time())
        self.last_input_at = time.time()
        self._processing = True

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
                await self._handle_velocity_frame(points, timestamp)
            else:
                await self._handle_profile_frame(source_id, points, timestamp)
            self.last_error = None
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"[{self.id}] Error processing frame from {source_id}: {e}", exc_info=True)
            notify_status_change(self.id)
        finally:
            self._processing = False

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

    def enable(self) -> None:
        notify_status_change(self.id)

    def disable(self) -> None:
        self._transition_to_idle()

    # ── Internal handlers ─────────────────────────────────────────────────

    async def _handle_velocity_frame(self, points: np.ndarray, timestamp: float) -> None:
        result = await asyncio.to_thread(self._velocity.update, points, timestamp)

        if result is None:
            return

        self.last_velocity = result.velocity

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

        position = self._velocity.current_position
        self._profiler.add_scan_line(sensor_id, points, position, timestamp)

    async def _finalize_profile(self) -> None:
        profile = await asyncio.to_thread(self._profiler.finish_vehicle)

        if profile is not None and len(profile.points) > 0:
            self._vehicles_counted += 1
            self.last_output_at = time.time()
            self.last_profile_points = len(profile.points)

            logger.info(
                f"[{self.id}] Vehicle #{self._vehicles_counted} profile complete: "
                f"{len(profile.points)} pts, {profile.scan_count} scans, "
                f"v_avg={profile.mean_velocity:.2f} m/s, "
                f"est_length={profile.estimated_length:.2f} m"
            )

            out_payload = {
                "node_id": self.id,
                "points": profile.points,
                "timestamp": profile.end_time,
                "count": len(profile.points),
                "metadata": {
                    "vehicle_number": self._vehicles_counted,
                    "scan_count": profile.scan_count,
                    "mean_velocity": profile.mean_velocity,
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
        self._velocity.reset_tracking()
        self.last_error = None
        notify_status_change(self.id)
