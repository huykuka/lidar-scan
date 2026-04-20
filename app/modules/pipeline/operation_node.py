from typing import Any, Dict, List, Optional
import asyncio
import concurrent.futures
import time
import numpy as np
from app.core.logging import get_logger
from app.modules.pipeline.operations import (
    Crop, Downsample, UniformDownsample,
    StatisticalOutlierRemoval, RadiusOutlierRemoval,
    PlaneSegmentation, PatchPlaneSegmentation,
    Clustering, Filter, FilterByKey,
    BoundaryDetection, DebugSave, SaveDataStructure,
    GeneratePlane, Densify,
)

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
    "save_structure": SaveDataStructure,
    "generate_plane": GeneratePlane,
    "densify": Densify,
    "patch_plane_segmentation": PatchPlaneSegmentation,
}

# Op types that are CPU-heavy and benefit from an isolated single-thread executor.
# A dedicated max_workers=1 executor:
#   (a) prevents these ops from starving the shared default ThreadPoolExecutor, and
#   (b) makes the skip-if-busy logic below equivalent to a natural single-slot queue.
_HEAVY_OP_TYPES = frozenset({"clustering", "patch_plane_segmentation", "plane_segmentation"})
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.nodes.shape_collector import ShapeCollectorMixin
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)

class OperationNode(ModuleNode, ShapeCollectorMixin):
    """
    A node that performs a single point cloud operation (e.g., Filtering, Downsampling).
    """
    def __init__(
        self,
        manager: Any,
        node_id: str,
        op_type: str,
        op_config: Dict[str, Any],
        name: Optional[str] = None,
        throttle_ms: float = 0  # Accepted but not used, handled by NodeManager
    ):
        ShapeCollectorMixin.__init__(self)
        self.manager = manager
        self.id = node_id
        self.name = name or node_id
        self.op_type = op_type
        
        # Instantiate the operation (op_config should not contain throttle_ms)
        try:
            op_class = _OP_MAP.get(op_type)
            if op_class is None:
                raise ValueError(f"Unknown operation type: '{op_type}'. Available: {list(_OP_MAP.keys())}")
            self.op = op_class(**op_config)
        except Exception as e:
            logger.error(f"[{self.id}] Failed to create operation '{op_type}': {e}")
            raise

        # Runtime stats
        self.last_input_at: Optional[float] = None
        self.last_output_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.processing_time_ms: float = 0.0
        self.input_count: int = 0
        self.output_count: int = 0
        self.last_metadata: Dict[str, Any] = {}  # Latest operation metadata for status reporting

        # Skip-if-busy guard: prevents frame backlog on slow nodes.
        # When True the node is running _sync_compute; any new frame is dropped.
        self._processing: bool = False

        # Heavy ops get an isolated single-thread executor so they can never
        # starve the shared default ThreadPoolExecutor used by lighter nodes.
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = (
            concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"op_{op_type}")
            if op_type in _HEAVY_OP_TYPES
            else None
        )

    async def on_input(self, payload: Dict[str, Any]):
        """Receives data, processes it, and forwards to downstream."""
        from app.modules.pipeline.base import PointConverter

        self.last_input_at = time.time()

        points = payload.get("points")
        if points is None or len(points) == 0:
            return

        # Skip-if-busy: drop this frame if a previous one is still running.
        # This prevents unbounded task accumulation when heavy nodes (e.g.
        # DBSCAN) are slower than the upstream sensor rate.
        if self._processing:
            logger.debug(f"[{self.id}] Dropping frame — node is still processing previous frame")
            return

        self._processing = True
        start_time = time.time()
        first_frame = self.input_count == 0
        self.input_count = len(points)

        try:
            # Move heavy CPU-bound Point Cloud operations to a background thread
            # so they don't block the main FastAPI/Websocket async event loop.
            def _sync_compute():
                # 1. Convert numpy -> Open3D t.PointCloud
                pcd_in = PointConverter.to_pcd(points)
                # 2. Apply the atomic operation
                outcome = self.op.apply(pcd_in)
                # Handle both (pcd, metadata) and raw pcd returns
                if isinstance(outcome, tuple):
                    pcd_out, op_result = outcome
                else:
                    pcd_out, op_result = outcome, {}
                # 3. Convert back to numpy for downstream
                return PointConverter.to_points(pcd_out), op_result

            # Open3D OpenGL contexts MUST strictly execute on the main thread
            # Background threading causes GTK / Wayland context explosions
            if self.op_type == "visualize":
                processed_points, op_metadata = _sync_compute()
            elif self._executor is not None:
                # Heavy op: use the dedicated single-thread executor so it
                # cannot starve the shared default executor.
                loop = asyncio.get_running_loop()
                processed_points, op_metadata = await loop.run_in_executor(
                    self._executor, _sync_compute
                )
            else:
                processed_points, op_metadata = await asyncio.to_thread(_sync_compute)
            
            if processed_points is None or len(processed_points) == 0:
                 return

            self.output_count = len(processed_points)
            self.processing_time_ms = (time.time() - start_time) * 1000
            self.last_output_at = time.time()
            self.last_error = None

            # Emit any shapes produced by the operation (e.g., Clustering with emit_shapes=True)
            # The 'shapes' key carries a list[ShapePayload]; pop it before status/payload work.
            pending_shapes = (op_metadata or {}).pop("shapes", None)
            if pending_shapes:
                for shape in pending_shapes:
                    self.emit_shape(shape)

            # Store metadata for status reporting (displayed on node badge)
            if op_metadata:
                self.last_metadata = op_metadata

            # Notify on first frame or when metadata changes
            if first_frame or op_metadata:
                notify_status_change(self.id)

            # Prepare payload for downstream
            new_payload = payload.copy()
            new_payload["points"] = processed_points
            new_payload["node_id"] = self.id
            new_payload["processed_by"] = self.id

            # Propagate operation metadata into the payload so downstream
            # nodes (e.g. IfConditionNode, OutputNode) can access operation
            # results like patch_count, inlier_count, cluster_count, etc.
            # - Top-level keys: for IfConditionNode expression evaluation
            # - "metadata" key: for OutputNode WebSocket JSON broadcast
            if op_metadata:
                new_payload.update(op_metadata)
                new_payload["metadata"] = op_metadata
            
            # Forward to downstream nodes via Manager (fire-and-forget)
            # NodeManager will handle WebSocket broadcasting automatically.
            # Decoupled so slow downstream nodes can't stall this producer.
            asyncio.create_task(self.manager.forward_data(self.id, new_payload))

        except Exception as e:
            self.last_error = str(e)
            notify_status_change(self.id)
            logger.error(f"[{self.id}] Error processing data: {e}", exc_info=True)
        finally:
            self._processing = False

    def emit_status(self) -> NodeStatusUpdate:
        """Return standardised status for this operation node.

        State mapping:
        - ``last_error`` set → ERROR, processing=False, gray, propagate error_message
        - Has metadata → RUNNING, show first metadata key/value, blue
        - Recent input within 5 s → RUNNING, processing=True, blue
        - Otherwise → RUNNING, processing=False, gray

        Returns:
            NodeStatusUpdate with operational_state and processing application_state
        """
        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(
                    label="processing",
                    value=False,
                    color="gray",
                ),
                error_message=self.last_error,
            )

        recently_active = (
            self.last_input_at is not None
            and time.time() - self.last_input_at < 5.0
        )

        # Show operation metadata as badge when available (e.g. "patches: 5")
        if self.last_metadata and recently_active:
            # Pick the most meaningful key to display
            label, value = next(iter(self.last_metadata.items()))
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
                application_state=ApplicationState(
                    label=label,
                    value=value,
                    color="blue",
                ),
            )

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="processing",
                value=recently_active,
                color="blue" if recently_active else "gray",
            ),
        )
