import asyncio
import concurrent.futures
import time
from typing import Any, Dict, Optional

import numpy as np

from app.core.logging import get_logger
from app.modules.pipeline.operations import (
    BoundaryDetection,
    CentroidCalculation,
    Clustering,
    CoordinateTransform,
    Crop,
    DebugSave,
    Densify,
    Downsample,
    EdgeDetection,
    Filter,
    FilterByKey,
    GeneratePlane,
    PatchPlaneSegmentation,
    PlaneProjection,
    PlaneSegmentation,
    RadiusOutlierRemoval,
    RangeImage,
    StatisticalOutlierRemoval,
    SurfaceReconstruction,
    UniformDownsample,
)
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.nodes.shape_collector import ShapeCollectorMixin
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)

_OP_MAP = {
    "crop": Crop,
    "downsample": Downsample,
    "uniform_downsample": UniformDownsample,
    "statistical_outlier_removal": StatisticalOutlierRemoval,
    "outlier_removal": StatisticalOutlierRemoval,
    "radius_outlier_removal": RadiusOutlierRemoval,
    "plane_segmentation": PlaneSegmentation,
    "clustering": Clustering,
    "filter": Filter,
    "filter_by_key": FilterByKey,
    "boundary_detection": BoundaryDetection,
    "debug_save": DebugSave,
    "generate_plane": GeneratePlane,
    "densify": Densify,
    "patch_plane_segmentation": PatchPlaneSegmentation,
    "surface_reconstruction": SurfaceReconstruction,
    "centroid_calculation": CentroidCalculation,
    "coordinate_transform": CoordinateTransform,
    "edge_detection": EdgeDetection,
    "plane_projection": PlaneProjection,
    "range_image": RangeImage,
}

# These ops are CPU-heavy (DBSCAN, RANSAC, ICP, mesh) and get a dedicated
# single-thread executor so they never starve the shared default pool.
_HEAVY_OP_TYPES = frozenset({
    "clustering",
    "patch_plane_segmentation",
    "plane_segmentation",
    "surface_reconstruction",
    "edge_detection",
})

_PRIMITIVE = (str, int, float, bool, type(None), list, dict)


class OperationNode(ModuleNode, ShapeCollectorMixin):
    """Applies a single point cloud operation inside a processing pipeline DAG.

    Dispatch strategy (fastest to slowest):
      1. ``apply_numpy`` present on op → run synchronously on event loop
         (~0.1 ms, no Open3D, no thread hop).
      2. ``PREFERS_LEGACY + apply_filter`` → numpy→legacy PCD→index select,
         still synchronous.
      3. Heavy op (in ``_HEAVY_OP_TYPES``) → dedicated single-thread executor
         so it cannot starve the shared pool.
      4. Everything else → shared ``asyncio.to_thread``.
      5. ``visualize`` op → always synchronous (OpenGL needs the main thread).
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        op_type: str,
        op_config: Dict[str, Any],
        name: Optional[str] = None,
        throttle_ms: float = 0,  # accepted but handled by NodeManager
    ) -> None:
        ShapeCollectorMixin.__init__(self)
        self.manager = manager
        self.id = node_id
        self.name = name or node_id
        self.op_type = op_type

        op_class = _OP_MAP.get(op_type)
        if op_class is None:
            raise ValueError(
                f"Unknown operation type: '{op_type}'. "
                f"Available: {list(_OP_MAP.keys())}"
            )
        try:
            self.op = op_class(**op_config)
        except Exception as e:
            logger.error("[%s] Failed to create operation '%s': %s", node_id, op_type, e)
            raise

        # Runtime stats
        self.last_input_at: Optional[float] = None
        self.last_output_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.processing_time_ms: float = 0.0
        self.input_count: int = 0
        self.output_count: int = 0
        self.last_metadata: Dict[str, Any] = {}

        # Skip-if-busy guard — drop incoming frame when still processing.
        self._processing: bool = False

        # Heavy ops get an isolated max_workers=1 executor.
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = (
            concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f"op_{op_type}"
            )
            if op_type in _HEAVY_OP_TYPES
            else None
        )

        # Pre-compute which dispatch path this op uses so on_input() has zero
        # branching overhead per frame.
        self._is_numpy_op: bool = hasattr(self.op, "apply_numpy")
        self._is_legacy_op: bool = (
            getattr(self.op, "PREFERS_LEGACY", False)
            and hasattr(self.op, "apply_filter")
        )
        self._is_visualize: bool = op_type == "visualize"

    # ------------------------------------------------------------------
    # Compute helpers
    # ------------------------------------------------------------------

    def _compute(self, points: np.ndarray) -> tuple:
        """Run the operation synchronously and return (out_points, metadata).

        Called either directly on the event loop (light ops) or from a
        background thread (heavy ops / standard Open3D ops).
        """
        from app.modules.pipeline.base import PointConverter

        # Fast path A: pure numpy, no Open3D at all (~0.1 ms).
        if self._is_numpy_op:
            return self.op.apply_numpy(points)

        # Fast path B: legacy PCD index-select, avoids Tensor allocation.
        if self._is_legacy_op:
            legacy_pcd = PointConverter.to_legacy_pcd(points)
            indices, meta = self.op.apply_filter(legacy_pcd)
            if indices is not None and len(indices) > 0:
                return points[indices], meta
            n_cols = points.shape[1] if points.ndim > 1 else 3
            return np.zeros((0, n_cols), dtype=np.float32), meta

        # Standard path: numpy → Open3D tensor PCD → op → numpy.
        pcd_in = PointConverter.to_pcd(points)
        outcome = self.op.apply(pcd_in)
        if isinstance(outcome, tuple):
            pcd_out, meta = outcome
        else:
            pcd_out, meta = outcome, {}
        return PointConverter.to_points(pcd_out), meta

    # ------------------------------------------------------------------
    # ModuleNode interface
    # ------------------------------------------------------------------

    async def on_input(self, payload: Dict[str, Any]) -> None:
        self.last_input_at = time.time()

        points = payload.get("points")
        if points is None or len(points) == 0:
            return

        # Drop frame if still processing previous one (back-pressure guard).
        if self._processing:
            logger.debug("[%s] Dropping frame — still processing previous frame", self.id)
            return

        self._processing = True
        start_time = time.time()
        first_frame = self.input_count == 0
        self.input_count = len(points)

        # Forward the WebSocket topic into ops that broadcast side-channel data.
        if hasattr(self.op, "_ws_topic"):
            self.op._ws_topic = getattr(self, "_ws_topic", None)

        try:
            # --- Dispatch ---------------------------------------------------
            if self._is_visualize or self._is_numpy_op or self._is_legacy_op:
                # Synchronous on the event loop:
                #   - visualize: OpenGL must stay on the main thread
                #   - numpy/legacy ops: fast enough (~0.1 ms) that a thread
                #     hop would cost more than the work itself
                processed_points, op_metadata = self._compute(points)

            elif self._executor is not None:
                # Heavy op: dedicated single-thread executor keeps it isolated
                # from the shared default pool.
                loop = asyncio.get_running_loop()
                processed_points, op_metadata = await loop.run_in_executor(
                    self._executor, self._compute, points
                )

            else:
                # Standard Open3D op: offload to shared thread pool so the
                # event loop stays responsive.
                processed_points, op_metadata = await asyncio.to_thread(
                    self._compute, points
                )
            # ----------------------------------------------------------------

            if processed_points is None or len(processed_points) == 0:
                return

            self.output_count = len(processed_points)
            self.processing_time_ms = (time.time() - start_time) * 1000
            self.last_output_at = time.time()
            self.last_error = None

            # Emit shapes produced by ops like Clustering.
            pending_shapes = (op_metadata or {}).pop("shapes", None)
            if pending_shapes:
                for shape in pending_shapes:
                    self.emit_shape(shape)

            # Keep only JSON-serialisable metadata (drop Open3D geometry objects).
            serializable_metadata: Dict[str, Any] = {
                k: v for k, v in (op_metadata or {}).items()
                if isinstance(v, _PRIMITIVE)
            }

            if serializable_metadata:
                self.last_metadata = serializable_metadata

            if first_frame or op_metadata:
                notify_status_change(self.id)

            new_payload = payload.copy()
            new_payload["points"] = processed_points
            new_payload["node_id"] = self.id
            new_payload["processed_by"] = self.id
            if serializable_metadata:
                new_payload.update(serializable_metadata)
                new_payload["metadata"] = serializable_metadata

            asyncio.create_task(self.manager.forward_data(self.id, new_payload))

        except Exception as e:
            self.last_error = str(e)
            notify_status_change(self.id)
            logger.error("[%s] Error processing data: %s", self.id, e, exc_info=True)
        finally:
            self._processing = False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def emit_status(self) -> NodeStatusUpdate:
        cycle_ms = round(self.processing_time_ms, 1) if self.processing_time_ms else None

        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(
                    label="processing", value=False, color="gray"
                ),
                error_message=self.last_error,
                cycle_time_ms=cycle_ms,
            )

        recently_active = (
            self.last_input_at is not None
            and time.time() - self.last_input_at < 5.0
        )

        if self.last_metadata and recently_active:
            label, value = next(iter(self.last_metadata.items()))
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
                application_state=ApplicationState(
                    label=label, value=value, color="blue"
                ),
                cycle_time_ms=cycle_ms,
            )

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="processing",
                value=recently_active,
                color="blue" if recently_active else "gray",
            ),
            cycle_time_ms=cycle_ms,
        )
