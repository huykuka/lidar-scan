"""
ObjectClassificationNode — Application-level DAG node for real-time object
detection and classification in LiDAR point clouds.

DAG wiring:
    [LiDAR Sensor] ──► [Crop/Downsample] ──► [Object Classification] ──► [Output]

Processing pipeline:
    1. Receive point cloud from upstream
    2. Run DBSCAN clustering to segment individual objects
    3. For each cluster, compute AABB dimensions
    4. Classify using rule-based size matching
    5. Emit labeled CubeShapes + LabelShapes for frontend overlay
    6. Forward classification metadata downstream

Architecture:
    - Heavy CPU-bound DBSCAN + classification runs in asyncio.to_thread()
    - Skip-if-busy: drops frames when previous classification is still running
    - Emits shapes via ShapeCollectorMixin for 3D visualization
    - Outputs structured metadata suitable for Output node webhook delivery
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import numpy as np
import open3d as o3d

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.nodes.shape_collector import ShapeCollectorMixin
from app.services.nodes.shapes import CubeShape, LabelShape
from app.services.status_aggregator import notify_status_change

from .utils.classifier import ClassificationResult, ObjectClassifier

logger = get_logger(__name__)


class ObjectClassificationNode(ModuleNode, ShapeCollectorMixin):
    """Real-time object classification node using DBSCAN + rule-based sizing.

    Clusters the incoming point cloud, measures each cluster's bounding box,
    and assigns a class label based on configurable dimension rules.

    Args:
        manager: NodeManager reference.
        node_id: Unique node ID.
        name: Display name.
        config: Node configuration dict from registry properties.
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        config: Dict[str, Any],
    ) -> None:
        ShapeCollectorMixin.__init__(self)
        self.manager = manager
        self.id = node_id
        self.name = name
        self._ws_topic: Optional[str] = None

        # DBSCAN parameters
        self._eps = float(config.get("eps", 0.3))
        self._min_cluster_points = int(config.get("min_cluster_points", 10))
        self._min_classify_points = int(config.get("min_classify_points", 5))

        # Classification filter
        self._show_unknown = bool(config.get("show_unknown", True))

        # Build classifier with default rules (configurable in future)
        self._classifier = ObjectClassifier(
            unknown_label="unknown",
            unknown_color="#888888",
        )

        # Runtime state
        self._is_processing = False
        self._classification_count = 0
        self._last_classification_at: Optional[float] = None
        self._last_results: List[ClassificationResult] = []
        self._last_error: Optional[str] = None
        self._frames_skipped = 0

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """Process incoming point cloud frame.

        Runs DBSCAN clustering + classification in a thread pool.
        Drops frames if the previous classification is still running.
        """
        if self._is_processing:
            self._frames_skipped += 1
            return

        points = payload.get("points")
        if points is None:
            return

        self._is_processing = True
        try:
            results = await asyncio.to_thread(self._sync_classify, points)

            self._last_results = results
            self._last_classification_at = time.time()
            self._classification_count += 1
            self._last_error = None

            # Emit shapes for each classified object
            for r in results:
                if not self._show_unknown and r.label == "unknown":
                    continue
                self.emit_shape(
                    CubeShape(
                        center=r.center,
                        size=r.size,
                        color=r.color,
                        opacity=0.4,
                        wireframe=True,
                        label=f"{r.label} ({r.point_count}pts)",
                    )
                )
                self.emit_shape(
                    LabelShape(
                        position=[
                            r.center[0],
                            r.center[1],
                            r.center[2] + r.size[2] / 2 + 0.2,
                        ],
                        text=r.label,
                        color=r.color,
                        font_size=12,
                    )
                )

            # Build metadata for downstream (Output node / webhook)
            metadata: Dict[str, Any] = {
                "classification_count": len(results),
                "objects": [
                    {
                        "label": r.label,
                        "confidence": r.confidence,
                        "center": r.center,
                        "size": r.size,
                        "point_count": r.point_count,
                    }
                    for r in results
                    if self._show_unknown or r.label != "unknown"
                ],
            }

            # Forward downstream
            await self.manager.forward_data(
                self.id,
                {
                    "node_id": self.id,
                    "timestamp": payload.get("timestamp", time.time()),
                    "points": points,
                    "metadata": metadata,
                },
            )

            notify_status_change(self.id)

        except Exception as e:
            self._last_error = str(e)
            logger.error(
                f"ObjectClassificationNode {self.id}: classification failed: {e}",
                exc_info=True,
            )
            notify_status_change(self.id)
        finally:
            self._is_processing = False

    def _sync_classify(self, points: np.ndarray) -> List[ClassificationResult]:
        """CPU-bound: cluster + classify (runs in thread pool).

        Args:
            points: (N, 3+) numpy array of point positions.

        Returns:
            List of classification results for detected clusters.
        """
        # Ensure we have at least XYZ columns
        if points.ndim != 2 or points.shape[1] < 3:
            return []

        positions = points[:, :3].astype(np.float64)

        if positions.shape[0] < self._min_cluster_points:
            return []

        # Build Open3D point cloud for DBSCAN
        pcd = o3d.t.geometry.PointCloud(
            o3d.core.Tensor(positions, dtype=o3d.core.float64)
        )

        # Run DBSCAN
        labels = pcd.cluster_dbscan(
            eps=self._eps,
            min_points=self._min_cluster_points,
            print_progress=False,
        )
        labels_np = labels.numpy()

        if labels_np.size == 0:
            return []

        cluster_count = int(labels_np.max()) + 1 if labels_np.max() >= 0 else 0
        if cluster_count == 0:
            return []

        # Classify all clusters
        results = self._classifier.classify_all(positions, labels_np, cluster_count)

        # Filter out clusters below the minimum point threshold
        results = [r for r in results if r.point_count >= self._min_classify_points]

        return results

    def emit_status(self) -> NodeStatusUpdate:
        """Return standardised status for this node.

        State mapping:
        - Error occurred → ERROR (red)
        - Currently processing → RUNNING (blue)
        - Classification within last 5s → RUNNING with object count (green)
        - Idle → RUNNING (gray)
        """
        if self._last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(
                    label="classification",
                    value="error",
                    color="red",
                ),
                error_message=self._last_error,
            )

        if self._is_processing:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
                application_state=ApplicationState(
                    label="classification",
                    value="processing",
                    color="blue",
                ),
            )

        if (
            self._last_classification_at is not None
            and time.time() - self._last_classification_at < 5.0
        ):
            obj_count = len(self._last_results)
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
                application_state=ApplicationState(
                    label="objects",
                    value=obj_count,
                    color="green" if obj_count > 0 else "gray",
                ),
            )

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="classification",
                value="idle",
                color="gray",
            ),
        )
