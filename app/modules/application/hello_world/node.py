"""
HelloWorldNode — example application-level DAG node.

Demonstrates the canonical application node pattern:
  1. Receive data via ``on_input()``.
  2. Perform lightweight processing (no heavy CPU — ``asyncio.to_thread``
     is not required for this example).
  3. Append metadata and forward the enriched payload downstream via
     ``manager.forward_data()``.
  4. Report node health via ``emit_status()``.
"""
from app.services.nodes.base_module import ModuleNode
import asyncio
import time
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)


class HelloWorldNode(ModuleNode):
    """
    Example application node that annotates and forwards point cloud payloads.

    Receives any point cloud payload from upstream DAG nodes, logs it,
    appends a custom ``app_message`` field together with the point count,
    and forwards the enriched payload to downstream nodes.
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        config: Dict[str, Any],
        throttle_ms: float = 0,
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name
        self.config = config
        self.message: str = config.get("message", "Hello from DAG!")

        # Runtime stats
        self.input_count: int = 0
        self.last_input_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.processing_time_ms: float = 0.0

    # ── Data flow ─────────────────────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        self.last_input_at = time.time()
        start_t = self.last_input_at

        points = payload.get("points")
        point_count: int = len(points) if points is not None else 0

        first_frame = self.input_count == 0
        self.input_count += 1

        logger.info(
            f"[{self.id}] on_input: {point_count} points "
            f"from node_id={payload.get('node_id')!r}. "
            f"message={self.message!r}"
        )

        try:
            # Build enriched payload (shallow copy to avoid mutating upstream data)
            new_payload = payload.copy()
            new_payload["node_id"] = self.id
            new_payload["processed_by"] = self.id
            new_payload["app_message"] = self.message
            new_payload["app_point_count"] = point_count

            self.processing_time_ms = (time.time() - start_t) * 1000
            self.last_error = None

            if first_frame:
                notify_status_change(self.id)

            # Fire-and-forget: prevents slow downstream nodes from stalling
            # this coroutine (matches OperationNode pattern).
            asyncio.create_task(self.manager.forward_data(self.id, new_payload))

        except Exception as exc:
            self.last_error = str(exc)
            notify_status_change(self.id)
            logger.error(f"[{self.id}] Error in on_input: {exc}", exc_info=True)

    # ── Status ────────────────────────────────────────────────────────────────

    def emit_status(self) -> NodeStatusUpdate:
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
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="processing",
                value=recently_active,
                color="blue" if recently_active else "gray",
            ),
        )
