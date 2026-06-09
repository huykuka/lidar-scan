"""
TruckBinDetectionNode — Real-time DAG node for open-top truck bin alignment.

Tracks the longitudinal alignment of cargo bins under a discharging nozzle
by analyzing unified 3D scans in real-time, executing robust 1D profile
peak and slope extraction, and tracking target stable thresholds.
"""

import asyncio
import enum
import time
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change

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
        results_service:  Optional results persistence service.
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        config: Dict[str, Any],
        results_service: Any = None,
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name
        self._ws_topic: Optional[str] = None
        self._results_service = results_service

        # Read configurations
        self._target_x = float(config.get("target_x", 0.0))
        self._tolerance = float(config.get("tolerance", 0.20))
        self._stable_duration = float(config.get("stable_duration", 1.0))

        # Build detector
        self._detector = BinDetector(
            lane_width=float(config.get("lane_width", 1.4)),
            z_min=float(config.get("z_min", 2.0)),
            z_max=float(config.get("z_max", 3.8)),
            cell_size=float(config.get("cell_size", 0.07)),
            z_wall_threshold=float(config.get("z_wall_threshold", 2.2)),
            z_cavity_max=float(config.get("z_cavity_max", 1.8)),
            min_bin_length=float(config.get("min_bin_length", 3.0)),
            max_bin_length=float(config.get("max_bin_length", 8.5)),
            target_x=self._target_x,
            tolerance=self._tolerance,
        )

        # State machine and status
        self._state = _State.IDLE
        self._detection_count: int = 0
        self._last_result: Optional[BinDetectionResult] = None

        # Temporal filter and stable-check state
        self._filtered_center: Optional[float] = None
        self._stable_start_time: Optional[float] = None

        # Node statistics
        self.last_input_at: Optional[float] = None
        self.last_output_at: Optional[float] = None
        self.last_error: Optional[str] = None
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
        notify_status_change(self.id)

        try:
            timestamp = payload.get("timestamp", time.time())

            # Execute heavy 1D geometry profile extraction in threadpool
            result = await asyncio.to_thread(self._detector.detect, points)

            if result.detected:
                # Apply 1D Temporal smoothing to prevent jitter
                if self._filtered_center is None:
                    self._filtered_center = result.x_center
                else:
                    self._filtered_center = (
                        0.7 * self._filtered_center + 0.3 * result.x_center
                    )

                result.x_center = self._filtered_center
                result.error_x = result.x_center - self._target_x

                # Determine Stable Alignment duration
                if abs(result.error_x) <= self._tolerance:
                    if self._stable_start_time is None:
                        self._stable_start_time = time.time()

                    elapsed = time.time() - self._stable_start_time
                    if elapsed >= self._stable_duration:
                        result.status = (
                            f"OK / STABLE — READY TO DISCHARGE ({elapsed:.1f}s)"
                        )
                    else:
                        result.status = f"STOP / ALIGNED — HOLDING ({elapsed:.1f}s)"
                else:
                    self._stable_start_time = None
                    if result.error_x > self._tolerance:
                        result.status = "REVERSE / BACK"
                    else:
                        result.status = "DRIVE FORWARD"

                self._detection_count += 1
                self.last_output_at = time.time()
                self._last_result = result

                logger.info(
                    "[%s] Bin center located: X=%.2f, error=%.2f m, status=%s",
                    self.id,
                    result.x_center,
                    result.error_x,
                    result.status,
                )

                # Forward detection results downstream
                out_payload: Dict[str, Any] = {
                    "node_id": self.id,
                    "points": result.bin_points,
                    "timestamp": timestamp,
                    "count": len(result.bin_points)
                    if result.bin_points is not None
                    else 0,
                    "metadata": {
                        "detection_number": self._detection_count,
                        "bin": result.to_dict(),
                    },
                }
                asyncio.create_task(self.manager.forward_data(self.id, out_payload))

                # Persistence
                if self._results_service is not None:
                    asyncio.create_task(self._persist_bin_result(result, out_payload))
            else:
                self._stable_start_time = None
                self._filtered_center = None
                self._last_result = result
                logger.debug(
                    "[%s] No valid bin cavity captured: %s", self.id, result.status
                )

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

        if self._last_result and self._last_result.detected:
            value = (
                f"{self._last_result.status} (Ex: {self._last_result.error_x:+.2f}m)"
            )
            if "STABLE" in self._last_result.status or "OK" in self._last_result.status:
                color = "green"
            elif "STOP" in self._last_result.status:
                color = "green"
            else:
                color = "orange"
        elif self._last_result:
            value = self._last_result.status
            color = "gray"
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
        self._filtered_center = None
        self._stable_start_time = None
        notify_status_change(self.id)

    def stop(self) -> None:
        self._state = _State.IDLE
        self._filtered_center = None
        self._stable_start_time = None
        self.last_error = None
        notify_status_change(self.id)

    async def _persist_bin_result(
        self, result: Any, out_payload: Dict[str, Any]
    ) -> None:
        """Persist bin detection result cloud + stats via ResultsStorageService."""
        try:
            import numpy as np
            import open3d as o3d

            def _build_pcd():
                pcd = o3d.geometry.PointCloud()
                pts = np.asarray(result.bin_points, dtype=np.float64)
                pcd.points = o3d.utility.Vector3dVector(pts)
                n = len(pts)
                # Assign distinct green/orange colors to target relative to status
                color = (
                    [0.1, 0.9, 0.1]
                    if "OK" in result.status or "STOP" in result.status
                    else [0.9, 0.5, 0.1]
                )
                pcd.colors = o3d.utility.Vector3dVector(np.tile(color, (n, 1)))
                return pcd

            bin_pcd = await asyncio.to_thread(_build_pcd)
            metadata = dict(out_payload.get("metadata", {}).get("bin", {}))
            metadata["detection_number"] = out_payload.get("metadata", {}).get(
                "detection_number"
            )
            result_id = await self._results_service.save_result(
                node_id=self.id,
                pcds=[("bin", bin_pcd)],
                metadata=metadata,
                status="success",
            )
            logger.info("[%s] Saved bin alignment result: %s", self.id, result_id)
        except Exception as exc:
            logger.error(
                "[%s] Failed to persist result: %s", self.id, exc, exc_info=True
            )
