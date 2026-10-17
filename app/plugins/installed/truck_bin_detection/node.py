"""
TruckBinDetectionNode — Real-time DAG node for open-top truck bin alignment.

Tracks the longitudinal alignment of cargo bins under a discharging nozzle
by analyzing unified 3D scans in real-time, executing robust 1D profile
peak and slope extraction, and tracking target stable thresholds.
"""

import asyncio
import enum
import time
from collections import deque
from typing import Any, Dict, Optional

import numpy as np

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change

from . import __version__
from .utils.bin_detector import BinDetectionResult, BinDetector

logger = get_logger(__name__)


class _State(enum.Enum):
    IDLE = "idle"
    DETECTING = "detecting"


class TruckBinDetectionNode(ModuleNode):
    """Real-time open-top bin edge tracking and positioning DAG node.

    Args:
        manager:          NodeManager reference.
        node_id:          Unique node ID.
        name:             Display name.
        config:           Node configuration properties.
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

        # Build detector
        self._detector = BinDetector(
            z_min=float(config.get("z_min", 2.0)),
            z_max=float(config.get("z_max", 3.8)),
            cell_size=float(config.get("cell_size", 0.07)),
            z_wall_threshold=float(config.get("z_wall_threshold", 2.2)),
            z_cavity_max=float(config.get("z_cavity_max", 1.8)),
            z_cavity_min=float(config.get("z_cavity_min", 0.5)),
            min_bin_area=float(config.get("min_bin_area", 2.0)),
            enable_area_check=bool(config.get("enable_area_check", True)),

            min_bin_length=float(config.get("min_bin_length", 3.0)),
            max_bin_length=float(config.get("max_bin_length", 8.5)),
            min_bed_cells=int(config.get("min_bed_cells", 3)),
            max_wall_thickness=float(config.get("max_wall_thickness", 0.5)),
            wall_height_match_tol=float(config.get("wall_height_match_tol", 0.04)),
            front_edge_lookahead=float(config.get("front_edge_lookahead", 0.3)),
            front_step_min=float(config.get("front_step_min", 0.3)),
            front_plateau_tol=float(config.get("front_plateau_tol", 0.15)),
            front_min_plateau_cells=int(config.get("front_min_plateau_cells", 1)),
            min_wall_cells=int(config.get("min_wall_cells", 3)),
        )

        # Bin length stabilisation: once stable, find the rear and place the front at rear + length
        self._stabilize_window = max(0.0, float(config.get("stabilize_window_s", 2.0)))
        self._stabilize_tol = float(config.get("stabilize_tolerance", 0.15))
        self._length_hist: deque = deque()  # (timestamp, length)
        self._locked_length: Optional[float] = None
        self._locked_wall_top: Optional[float] = None
        self._last_hit_at: float = 0.0

        # State machine and status
        self._state = _State.IDLE
        self._detection_count: int = 0
        self._last_result: Optional[BinDetectionResult] = None

        # Temporal filter state
        self._filtered_center: Optional[float] = None

        # Node statistics
        self.last_input_at: Optional[float] = None
        self.last_output_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.processing_time_ms: float = 0.0
        self._processing: bool = False

    # ── ModuleNode interface ──────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        points = payload.get("points")
        if points is None or len(points) == 0:
            return

        # Processing guard
        if self._processing:
            return

        self.last_input_at = time.time()
        self._processing = True
        self._state = _State.DETECTING
        start_time = time.time()
        notify_status_change(self.id)

        try:
            timestamp = payload.get("timestamp", time.time())

            # detect() runs in ~0.1-0.4 ms — fast enough to run directly on
            # the event loop without dispatching to a thread.  asyncio.to_thread
            # adds 1-5 ms of scheduling overhead (GIL, context switch, thread
            # pool latency) which dominates the actual compute time.
            now = time.time()
            result = self._detector.detect(
                points,
                known_length=self._locked_length,
                known_wall_top=self._locked_wall_top,
            )
            self._update_length_lock(result, now)
            self.processing_time_ms = (time.time() - start_time) * 1000

            if result.detected:
                # Apply 1D temporal smoothing to prevent jitter
                if self._filtered_center is None:
                    self._filtered_center = result.x_center
                else:
                    self._filtered_center = (
                        0.7 * self._filtered_center + 0.3 * result.x_center
                    )

                result.x_center = self._filtered_center

                self._detection_count += 1
                self.last_output_at = time.time()
                self._last_result = result

                # Forward raw detection results downstream — positioning logic is external
                out_payload: Dict[str, Any] = {
                    "node_id": self.id,
                    "points": result.bin_points,
                    "timestamp": timestamp,
                    "count": len(result.bin_points)
                    if result.bin_points is not None
                    else 0,
                    "pcds": {
                        "bin": result.bin_points,
                    },
                    "metadata": {
                        "plugin_version": __version__,
                        "detection_number": self._detection_count,
                        "bin": result.to_dict(),
                    },
                }
                asyncio.create_task(self.manager.forward_data(self.id, out_payload))
            else:
                self._filtered_center = None
                self._last_result = result
                logger.debug(
                    "[%s] No valid bin cavity captured: %s", self.id, result.status
                )
                # Emit an empty payload so downstream consumers (WebSocket
                # broadcast, point-cloud visualisation) clear stale data from
                # the previous successful detection rather than keeping it on
                # screen indefinitely.
                _empty = np.empty((0, 3), dtype=np.float32)
                empty_payload: Dict[str, Any] = {
                    "node_id": self.id,
                    "points": _empty,
                    "timestamp": timestamp,
                    "count": 0,
                    "pcds": {"bin": _empty},
                    "metadata": {
                        "plugin_version": __version__,
                        "detection_number": self._detection_count,
                        "bin": result.to_dict(),
                    },
                }
                asyncio.create_task(self.manager.forward_data(self.id, empty_payload))

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

    def _reset_length_lock(self) -> None:
        self._length_hist.clear()
        self._locked_length = None
        self._locked_wall_top = None

    def _update_length_lock(self, result: BinDetectionResult, now: float) -> None:
        """Track the bin length over the stabilize window and lock it once stable."""
        if self._stabilize_window <= 0:
            return
        if not result.detected:
            # Tolerate short drop-outs; a long one means the truck has left.
            if now - self._last_hit_at > self._stabilize_window:
                self._reset_length_lock()
            return
        self._last_hit_at = now
        if self._locked_length is not None:
            return  # length stays locked; only the rear is searched
        hist = self._length_hist
        hist.append((now, result.length))
        while hist and now - hist[0][0] > self._stabilize_window:
            hist.popleft()
        # Window must be fully covered by samples (oldest ~ window old).
        if len(hist) < 3 or now - hist[0][0] < self._stabilize_window * 0.9:
            return
        lengths = [l for _, l in hist]
        if max(lengths) - min(lengths) <= self._stabilize_tol:
            self._locked_length = float(np.median(lengths))
            self._locked_wall_top = result.wall_top
            logger.info("[%s] Bin length locked at %.3f m", self.id, self._locked_length)

    def emit_status(self) -> NodeStatusUpdate:
        cycle_ms = round(self.processing_time_ms, 1) if self.processing_time_ms else None

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
                cycle_time_ms=cycle_ms,
            )

        if self._state == _State.DETECTING:
            return NodeStatusUpdate(
                node_id=self.id,
                error_message=None,
                operational_state=OperationalState.RUNNING,
                application_state=ApplicationState(
                    label="state",
                    value="detecting",
                    color="blue",
                ),
                cycle_time_ms=cycle_ms,
            )

        if self._last_result and self._last_result.detected:
            value = (
                f"{self._last_result.status} (X: {self._last_result.x_center:+.2f}m)"
            )
            color = "green"
        elif self._last_result:
            value = self._last_result.status
            color = "gray"
        else:
            value = "idle"
            color = "gray"

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            error_message=None,
            application_state=ApplicationState(
                label="state",
                value=value,
                color=color,
            ),
            cycle_time_ms=cycle_ms,
        )

    def start(self, data_queue: Any = None, runtime_status: Any = None) -> None:
        self._filtered_center = None
        self._reset_length_lock()
        notify_status_change(self.id)

    def stop(self) -> None:
        self._state = _State.IDLE
        self._filtered_center = None
        self._reset_length_lock()
        self.last_error = None
        notify_status_change(self.id)


