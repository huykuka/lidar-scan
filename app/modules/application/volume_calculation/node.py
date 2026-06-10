"""
VolumeCalculationNode — DAG node for payload volume estimation.

DAG wiring:
    [PCD Injection (empty)]  ──┐
                               ├──► [Volume Calculation] ──► volume result
    [PCD Injection (loaded)] ──┘

State machine
-------------
Inputs arrive as POST-injected PCD pairs.  Whichever cloud of the pair
arrives second triggers the calculation; both buffers are cleared
afterwards so the node is ready for the next pair.

    IDLE
     ├─(empty arrives)──► WAITING_FOR_LOADED
     ├─(loaded arrives)─► WAITING_FOR_EMPTY
    WAITING_FOR_LOADED
     └─(loaded arrives)─► calculate → emit → IDLE
    WAITING_FOR_EMPTY
     └─(empty arrives)──► calculate → emit → IDLE

The sensor whose node-ID matches ``empty_sensor_id`` in config is treated
as the empty input; all other connected sensors are treated as loaded.

Output payload
--------------
``forward_data`` is called with::

    {
        "node_id":    str,
        "timestamp":  float,
        "volume_m3":  float,
        "volume_l":   float,
        "cell_count": int,
        "icp_valid":  bool,
        "icp_fitness": float,
        "pcds": {
            "empty":  np.ndarray,
            "loaded": np.ndarray,
        },
        "metadata": {
            "volume_m3":           float,
            "volume_l":            float,
            "icp_fitness":         float,
            "icp_valid":           bool,
            "cell_count":          int,
            "grid_res":            float,
            "icp_rmse":            float,
            "calculation_number":  int,
        },
    }
"""
import asyncio
import enum
import time
from typing import Any, Dict, Optional

import numpy as np

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change

from .utils.calculator import VolumeCalculator

logger = get_logger(__name__)


class _State(enum.Enum):
    IDLE                = "idle"
    WAITING_FOR_LOADED  = "waiting for loaded"
    WAITING_FOR_EMPTY   = "waiting for empty"
    CALCULATING         = "calculating"


_STATE_COLOR = {
    _State.IDLE:               "gray",
    _State.WAITING_FOR_LOADED: "orange",
    _State.WAITING_FOR_EMPTY:  "orange",
    _State.CALCULATING:        "blue",
}


class VolumeCalculationNode(ModuleNode):
    """Estimate the volume of material on a surface by comparing a pair of
    injected point clouds — one empty baseline, one loaded state.

    Each calculation consumes the pair and resets to IDLE so the node is
    ready for the next injection pair.

    Args:
        manager:          NodeManager reference.
        node_id:          Unique node ID.
        name:             Display name.
        empty_sensor_id:  Node ID of the sensor / injection node that supplies
                          the empty baseline cloud.
        config:           Node configuration dict (from registry properties).
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        empty_sensor_id: str,
        config: Dict[str, Any],
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name
        self._empty_sensor_id = empty_sensor_id

        self._calculator = VolumeCalculator(
            voxel_size=float(config.get("voxel_size", 0.005)),
            outlier_nb_neighbors=int(config.get("outlier_nb_neighbors", 20)),
            outlier_std_ratio=float(config.get("outlier_std_ratio", 2.0)),
            remove_ground=bool(config.get("remove_ground", True)),
            ground_distance_threshold=float(config.get("ground_distance_threshold", 0.01)),
            ground_ransac_n=int(config.get("ground_ransac_n", 3)),
            ground_num_iterations=int(config.get("ground_num_iterations", 1000)),
            icp_max_correspondence=float(config.get("icp_max_correspondence", 0.05)),
            min_icp_fitness=float(config.get("min_icp_fitness", 0.3)),
            grid_res=float(config.get("grid_res", 0.005)),
            delta_threshold=float(config.get("delta_threshold", 0.02)),
            morph_open_iterations=int(config.get("morph_open_iterations", 2)),
        )

        # Pair buffers — both cleared after each calculation
        self._empty_pts: Optional[np.ndarray] = None
        self._loaded_pts: Optional[np.ndarray] = None
        self._empty_ts: Optional[float] = None
        self._loaded_ts: Optional[float] = None

        # State machine
        self._state = _State.IDLE

        # Runtime stats
        self.last_input_at: Optional[float] = None
        self.last_output_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.last_volume_m3: Optional[float] = None
        self._calculation_count: int = 0

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
            is_empty = source_id == self._empty_sensor_id

            if is_empty:
                self._empty_pts = np.asarray(points, dtype=np.float64)
                self._empty_ts = timestamp
                logger.debug("[%s] Empty cloud received (%d pts)", self.id, len(self._empty_pts))
            else:
                self._loaded_pts = np.asarray(points, dtype=np.float64)
                self._loaded_ts = timestamp
                logger.debug("[%s] Loaded cloud received (%d pts)", self.id, len(self._loaded_pts))

            # Advance state machine
            if self._state == _State.CALCULATING:
                logger.warning(
                    "[%s] Received new cloud while calculation in progress — "
                    "cloud buffered, will be used in next pair",
                    self.id,
                )
                return

            pair_complete = self._empty_pts is not None and self._loaded_pts is not None

            if pair_complete:
                await self._run_calculation()
            else:
                # Transition to waiting state so UI reflects what's missing
                self._state = (
                    _State.WAITING_FOR_LOADED if is_empty else _State.WAITING_FOR_EMPTY
                )
                notify_status_change(self.id)

            self.last_error = None
        except Exception as e:
            self.last_error = str(e)
            logger.error("[%s] Error processing input from %s: %s", self.id, source_id, e, exc_info=True)
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

        value = self._state.value
        if self._state == _State.IDLE and self.last_volume_m3 is not None:
            value = f"{self.last_volume_m3 * 1000:.1f} L"

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="state",
                value=value,
                color=_STATE_COLOR.get(self._state, "gray"),
            ),
        )

    def start(self, data_queue: Any = None, runtime_status: Any = None) -> None:
        notify_status_change(self.id)

    def stop(self) -> None:
        self._reset_buffers()
        self._state = _State.IDLE
        notify_status_change(self.id)

    # ── Internal ──────────────────────────────────────────────────────────

    def _reset_buffers(self) -> None:
        self._empty_pts = None
        self._loaded_pts = None
        self._empty_ts = None
        self._loaded_ts = None

    async def _run_calculation(self) -> None:
        self._state = _State.CALCULATING
        notify_status_change(self.id)

        # Snapshot and immediately clear buffers so the next pair can be
        # received while the (potentially slow) calculation runs
        empty_pts = self._empty_pts.copy()   # type: ignore[union-attr]
        loaded_pts = self._loaded_pts.copy()  # type: ignore[union-attr]
        # Use the later of the two timestamps as the output timestamp
        timestamp = max(self._empty_ts or 0.0, self._loaded_ts or 0.0)
        self._reset_buffers()

        try:
            result = await asyncio.to_thread(
                self._calculator.calculate, empty_pts, loaded_pts
            )

            self._calculation_count += 1
            self.last_volume_m3 = result.volume_m3
            self.last_output_at = time.time()

            logger.info(
                "[%s] Pair #%d → %.6f m³  (%.3f L)  icp_valid=%s  cells=%d",
                self.id, self._calculation_count,
                result.volume_m3, result.volume_l,
                result.icp_valid, result.cell_count,
            )

            out_payload: Dict[str, Any] = {
                "node_id": self.id,
                "timestamp": timestamp,
                "volume_m3": result.volume_m3,
                "volume_l": result.volume_l,
                "cell_count": result.cell_count,
                "icp_valid": result.icp_valid,
                "icp_fitness": result.icp_fitness,
                "pcds": {
                    "empty": empty_pts,
                    "loaded": loaded_pts,
                },
                "metadata": {
                    "volume_m3": result.volume_m3,
                    "volume_l": result.volume_l,
                    "icp_fitness": result.icp_fitness,
                    "icp_valid": result.icp_valid,
                    "cell_count": result.cell_count,
                    "grid_res": result.grid_res,
                    "icp_rmse": result.icp_rmse,
                    "calculation_number": self._calculation_count,
                },
            }
            asyncio.create_task(self.manager.forward_data(self.id, out_payload))

        except Exception as exc:
            self.last_error = str(exc)
            logger.error("[%s] Volume calculation failed: %s", self.id, exc, exc_info=True)
        finally:
            self._state = _State.IDLE
            notify_status_change(self.id)
