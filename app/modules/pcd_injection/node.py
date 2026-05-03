"""
PCD Injection node — DAG source node that accepts PCD data via REST multipart upload.

External clients POST PCD files to the /api/v1/pcd-injection/{node_id}/upload endpoint.
The parsed point cloud is forwarded into the DAG exactly like a hardware sensor frame.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

import numpy as np

from app.core.logging import get_logger
from app.services.nodes.base_module import ModuleNode
from app.schemas.status import NodeStatusUpdate, OperationalState, ApplicationState
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)


class PcdInjectionNode(ModuleNode):
    """Source node that receives PCD data via HTTP multipart upload.

    Unlike hardware sensor nodes this node has no background worker process.
    Data is pushed in on-demand through :meth:`inject_points`, which is called
    by the REST handler after parsing the uploaded PCD file.
    """

    id: str
    name: str
    manager: Any

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        topic_prefix: str,
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name
        self.topic_prefix = topic_prefix

        # Runtime counters
        self._frames_injected: int = 0
        self._last_inject_at: Optional[float] = None
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # ModuleNode interface
    # ------------------------------------------------------------------

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """PCD Injection is a source node — it does not receive upstream input."""

    def emit_status(self) -> NodeStatusUpdate:
        operational_state = OperationalState.RUNNING
        app_value = "ready"
        app_color = "green"

        if self._last_error:
            operational_state = OperationalState.ERROR
            app_value = "error"
            app_color = "red"
        elif self._frames_injected == 0:
            app_value = "waiting"
            app_color = "gray"

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=operational_state,
            application_state=ApplicationState(
                label="injection_status",
                value=app_value,
                color=app_color,
            ),
            error_message=self._last_error,
        )

    # ------------------------------------------------------------------
    # Injection API
    # ------------------------------------------------------------------

    async def inject_points(self, points: np.ndarray) -> int:
        """Inject a parsed point cloud into the DAG.

        Args:
            points: (N, 3) float32/float64 numpy array of XYZ coordinates.

        Returns:
            Number of points forwarded.
        """
        try:
            now = time.time()
            payload: Dict[str, Any] = {
                "points": points,
                "timestamp": now,
                "node_id": self.id,
            }
            self._frames_injected += 1
            self._last_inject_at = now
            self._last_error = None

            asyncio.create_task(self.manager.forward_data(self.id, payload))
            notify_status_change(self.id)

            logger.debug(
                "[%s] Injected frame #%d (%d points)",
                self.id, self._frames_injected, len(points),
            )
            return len(points)
        except Exception as exc:
            self._last_error = str(exc)
            notify_status_change(self.id)
            logger.error("[%s] Injection failed: %s", self.id, exc, exc_info=True)
            raise
