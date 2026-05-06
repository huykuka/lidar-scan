"""
TruckBinDetectionNode — Application-level DAG node for detecting and measuring
the cargo bin of open-top dump trucks from 3D point cloud data.

DAG wiring:
    [Vehicle Profiler] ──► [Truck Bin Detection] ──► bin cloud + metadata
    [LiDAR Sensor]     ──► [Truck Bin Detection] ──► bin cloud + metadata

State machine:
    IDLE ──(cloud received)──► DETECTING ──(analysis done)──► IDLE

Architecture:
    - ``on_input`` receives a point cloud payload (from Vehicle Profiler or
      any upstream sensor/pipeline node).
    - Heavy Open3D processing runs in ``asyncio.to_thread()`` to avoid
      blocking the FastAPI event loop.
    - Results are forwarded via ``manager.forward_data`` and broadcast
      via WebSocket for real-time visualization.
"""
import asyncio
import enum
import time
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change

from .utils.bin_detector import BinDetector, BinDetectionResult

logger = get_logger(__name__)


class _State(enum.Enum):
    IDLE = "idle"
    DETECTING = "detecting"


class TruckBinDetectionNode(ModuleNode):
    """Detects and measures open-top dump truck cargo bins from point clouds.

    Args:
        manager:   NodeManager reference.
        node_id:   Unique node ID.
        name:      Display name.
        config:    Node configuration dict (from registry properties).
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        config: Dict[str, Any],
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name
        self._ws_topic: Optional[str] = None

        # Build detector from config
        self._detector = BinDetector(
            min_bin_length=float(config.get("min_bin_length", 2.0)),
            min_bin_width=float(config.get("min_bin_width", 1.5)),
            min_bin_height=float(config.get("min_bin_height", 0.5)),
            floor_distance_threshold=float(config.get("floor_distance_threshold", 0.05)),
            wall_distance_threshold=float(config.get("wall_distance_threshold", 0.05)),
            floor_ransac_n=int(config.get("floor_ransac_n", 3)),
            floor_ransac_iterations=int(config.get("floor_ransac_iterations", 1000)),
            wall_min_points=int(config.get("wall_min_points", 50)),
            voxel_size=float(config.get("voxel_size", 0.02)),
            vertical_tolerance_deg=float(config.get("vertical_tolerance_deg", 30.0)),
            horizontal_tolerance_deg=float(config.get("horizontal_tolerance_deg", 15.0)),
            intersection_tolerance=float(config.get("intersection_tolerance", 0.5)),
        )

        # State machine
        self._state = _State.IDLE
        self._detection_count: int = 0
        self._last_result: Optional[BinDetectionResult] = None

        # Runtime stats
        self.last_input_at: Optional[float] = None
        self.last_output_at: Optional[float] = None
        self.last_error: Optional[str] = None

        # Processing guard
        self._processing: bool = False

    # ── ModuleNode interface ──────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        points = payload.get("points")
        if points is None or len(points) == 0:
            return

        # Skip if already processing (non-blocking guard)
        if self._processing:
            return

        self.last_input_at = time.time()
        self._processing = True
        self._state = _State.DETECTING
        notify_status_change(self.id)

        try:
            timestamp = payload.get("timestamp", time.time())
            result = await asyncio.to_thread(self._detector.detect, points)
            self._last_result = result

            if result.detected:
                self._detection_count += 1
                self.last_output_at = time.time()

                logger.info(
                    "[%s] Bin detected #%d: L=%.2f W=%.2f H=%.2f vol=%.2f m³",
                    self.id, self._detection_count,
                    result.length, result.width, result.height, result.volume,
                )

                # Forward segmented bin cloud + metadata downstream
                # (the routing manager handles WS broadcasting internally)
                out_payload: Dict[str, Any] = {
                    "node_id": self.id,
                    "points": result.bin_points,
                    "timestamp": timestamp,
                    "count": len(result.bin_points) if result.bin_points is not None else 0,
                    "metadata": {
                        "detection_number": self._detection_count,
                        "bin": result.to_dict(),
                    },
                }
                asyncio.create_task(self.manager.forward_data(self.id, out_payload))
            else:
                logger.debug("[%s] No bin detected in input cloud", self.id)

            self.last_error = None
        except Exception as e:
            self.last_error = str(e)
            logger.error(
                "[%s] Error during bin detection: %s", self.id, e, exc_info=True
            )
        finally:
            self._processing = False
            self._state = _State.IDLE
            notify_status_change(self.id)

    def emit_status(self) -> NodeStatusUpdate:
        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(
                    label="state",
                    value="error",
                    color="red",
                ),
                error_message=self.last_error,
            )

        if self._state == _State.DETECTING:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
                application_state=ApplicationState(
                    label="state",
                    value="detecting",
                    color="blue",
                ),
            )

        # IDLE state — show last detection result
        if self._last_result and self._last_result.detected:
            value = (
                f"detected (#{self._detection_count}: "
                f"{self._last_result.length:.1f}×"
                f"{self._last_result.width:.1f}×"
                f"{self._last_result.height:.1f}m)"
            )
            color = "green"
        elif self._last_result and not self._last_result.detected:
            value = "no bin"
            color = "orange"
        else:
            value = "idle"
            color = "gray"

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="state",
                value=value,
                color=color,
            ),
        )

    def start(self, data_queue: Any = None, runtime_status: Any = None) -> None:
        notify_status_change(self.id)

    def stop(self) -> None:
        self._state = _State.IDLE
        self.last_error = None
        notify_status_change(self.id)


