"""
ResultStorageNode — Terminal sink DAG node that persists point-cloud results
and metadata via :class:`~app.services.results_storage.ResultsStorageService`.

DAG wiring:
    [Application Node] ──► [Result Storage]  (terminal — no downstream)

Payload conventions:
    The node understands two payload shapes from upstream application nodes:

    1. **Single PCD** — ``payload["points"]`` is an ``np.ndarray``.
       Stored as a single PCD file labeled ``"result"`` (or the source node type).

    2. **Multi PCD** — ``payload["pcds"]`` is a ``Dict[str, np.ndarray]``,
       mapping label names to point arrays.  Each entry becomes a separate
       PCD file in the result directory.

    Metadata is read from ``payload.get("metadata", {})``.

    Result status is derived from the configurable ``status_key`` metadata
    field, or falls back to ``default_status``.
"""
import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import open3d as o3d

from app.core.logging import get_logger
from app.schemas.results import pcd_color_for_label
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)


class ResultStorageNode(ModuleNode):
    """Terminal sink node that persists application results to disk + DB.

    Args:
        manager:          NodeManager reference.
        node_id:          Unique node ID.
        name:             Display name.
        config:           Node configuration dict (from registry properties).
        results_service:  ResultsStorageService instance (may be None if unavailable).
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
        self._results_service = results_service

        self._default_status: str = config.get("default_status", "success")
        self._status_key: str = config.get("status_key", "") or ""

        # Runtime stats
        self.last_input_at: Optional[float] = None
        self.last_save_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self._save_count: int = 0

    # ── ModuleNode interface ──────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        self.last_input_at = time.time()

        if self._results_service is None:
            self.last_error = "Results service unavailable"
            logger.error("[%s] Results service is not available", self.id)
            notify_status_change(self.id)
            return

        try:
            pcds = self._extract_pcds(payload)
            if not pcds:
                logger.debug("[%s] No point cloud data in payload — skipping", self.id)
                return

            metadata = self._extract_metadata(payload)
            status = self._derive_status(metadata)

            o3d_pcds = await asyncio.to_thread(self._build_o3d_pcds, pcds)

            result_id = await self._results_service.save_result(
                node_id=self.id,
                pcds=o3d_pcds,
                metadata=metadata,
                status=status,
            )

            self._save_count += 1
            self.last_save_at = time.time()
            self.last_error = None
            logger.info(
                "[%s] Saved result %s (%d PCDs, status=%s)",
                self.id, result_id, len(o3d_pcds), status,
            )
            notify_status_change(self.id)

        except Exception as exc:
            self.last_error = str(exc)
            logger.error("[%s] Failed to persist result: %s", self.id, exc, exc_info=True)
            notify_status_change(self.id)

    def emit_status(self) -> NodeStatusUpdate:
        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                error_message=self.last_error,
            )

        if self.last_save_at is None:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
            )

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="saved",
                value=self._save_count,
                color="blue" if (time.time() - self.last_save_at) < 5.0 else "gray",
            ),
        )

    def start(self, data_queue: Any = None, runtime_status: Any = None) -> None:
        notify_status_change(self.id)

    def stop(self) -> None:
        notify_status_change(self.id)

    # ── Payload extraction ────────────────────────────────────────────────

    @staticmethod
    def _extract_pcds(payload: Dict[str, Any]) -> Dict[str, np.ndarray]:
        """Extract named point clouds from the payload.

        Supports two conventions:
        - ``payload["pcds"]``: Dict[str, ndarray]  (multi-PCD, preferred)
        - ``payload["points"]``: ndarray            (single-PCD fallback)
        """
        pcds_raw = payload.get("pcds")
        if isinstance(pcds_raw, dict) and pcds_raw:
            return {
                label: np.asarray(pts, dtype=np.float64)
                for label, pts in pcds_raw.items()
                if pts is not None and len(pts) > 0
            }

        points = payload.get("points")
        if points is not None and len(points) > 0:
            label = "result"
            return {label: np.asarray(points, dtype=np.float64)}

        return {}

    @staticmethod
    def _extract_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata dict from the payload."""
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            return dict(metadata)
        # Gather top-level scalar fields as metadata (exclude binary/internal)
        skip_keys = {"points", "pcds", "node_id", "timestamp", "lidar_id", "count"}
        return {
            k: v for k, v in payload.items()
            if k not in skip_keys and isinstance(v, (str, int, float, bool))
        }

    def _derive_status(self, metadata: Dict[str, Any]) -> str:
        """Derive result status from metadata or fall back to default."""
        if self._status_key and self._status_key in metadata:
            return "success" if metadata[self._status_key] else "warning"
        return self._default_status

    @staticmethod
    def _build_o3d_pcds(
        pcds: Dict[str, np.ndarray],
    ) -> List[Tuple[str, o3d.geometry.PointCloud]]:
        """Convert raw numpy arrays to coloured Open3D PointCloud objects."""
        result: List[Tuple[str, o3d.geometry.PointCloud]] = []
        for label, pts in pcds.items():
            pcd = o3d.geometry.PointCloud()
            pts_arr = np.asarray(pts, dtype=np.float64)
            if pts_arr.ndim == 2 and pts_arr.shape[1] >= 3:
                pcd.points = o3d.utility.Vector3dVector(pts_arr[:, :3])
            else:
                pcd.points = o3d.utility.Vector3dVector(pts_arr)

            # Apply canonical color for the label
            n = len(pcd.points)
            if n > 0:
                hex_color = pcd_color_for_label(label)
                r = int(hex_color[1:3], 16) / 255.0
                g = int(hex_color[3:5], 16) / 255.0
                b = int(hex_color[5:7], 16) / 255.0
                pcd.colors = o3d.utility.Vector3dVector(
                    np.tile([r, g, b], (n, 1))
                )
            result.append((label, pcd))
        return result
