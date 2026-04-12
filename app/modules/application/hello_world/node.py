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
import asyncio
import time
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.modules.application.base_node import ApplicationNode
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)


class HelloWorldNode(ApplicationNode):
    """
    Example application node that annotates and forwards point cloud payloads.

    Receives any point cloud payload from upstream DAG nodes, logs it,
    appends a custom ``app_message`` field together with the point count,
    and forwards the enriched payload to downstream nodes.

    Attributes:
        id (str): Unique node instance identifier (from ``node_id``).
        name (str): Display name for this node.
        manager (Any): NodeManager reference used for ``forward_data()``.
        config (Dict[str, Any]): Full config dict from the persisted node
            record.
        message (str): Custom message string extracted from ``config``;
            defaults to ``"Hello from DAG!"``.
        input_count (int): Running count of payloads received.
        last_input_at (Optional[float]): Unix timestamp of the most recent
            ``on_input()`` call; ``None`` until first frame.
        last_error (Optional[str]): String representation of the last
            exception raised inside ``on_input()``; ``None`` when healthy.
        processing_time_ms (float): Wall-clock duration of the most recent
            ``on_input()`` execution in milliseconds.
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        config: Dict[str, Any],
        throttle_ms: float = 0,
    ) -> None:
        """
        Initialise the HelloWorldNode.

        Args:
            manager:     NodeManager instance injected by the registry factory.
            node_id:     Unique identifier for this node instance (from the DB).
            name:        Human-readable display name.
            config:      Full configuration dictionary from the persisted node
                         record.  Recognised keys:

                         * ``"message"`` (str) — greeting appended to each
                           forwarded payload.
                         * ``"throttle_ms"`` (int | float) — accepted for
                           interface compatibility; throttling is enforced
                           centrally by ``ThrottleManager``.
            throttle_ms: Accepted for interface compatibility; not stored or
                         used — the central ``ThrottleManager`` enforces it.
        """
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

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(
        self,
        data_queue: Any = None,
        runtime_status: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called by ``LifecycleManager.start_all_nodes()`` at DAG startup.

        Logs a startup message.  No background process is spawned here
        (unlike hardware sensor nodes).

        Args:
            data_queue:     Unused; accepted for interface compatibility.
            runtime_status: Unused; accepted for interface compatibility.
        """
        logger.info(
            f"[{self.id}] HelloWorldNode '{self.name}' started. "
            f"message={self.message!r}"
        )

    def stop(self) -> None:
        """
        Called by ``LifecycleManager.stop_all_nodes()`` at DAG shutdown.

        Logs a shutdown message.  No resources need to be released.
        """
        logger.info(f"[{self.id}] HelloWorldNode '{self.name}' stopped.")

    # ── Data flow ─────────────────────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """
        Receive a payload from an upstream node, annotate it, and forward it.

        Processing steps (per api-spec.md § 1.2):
          1. Record ``self.last_input_at``.
          2. Extract ``points`` and compute ``point_count``.
          3. Increment ``self.input_count``.
          4. Log at INFO.
          5. Build ``new_payload = payload.copy()`` (shallow copy).
          6. Annotate ``new_payload`` with ``node_id``, ``processed_by``,
             ``app_message``, ``app_point_count``.
          7. Fire-and-forget ``manager.forward_data()`` via
             ``asyncio.create_task()``.
          8. On first frame: call ``notify_status_change()``.
          9. On exception: set ``self.last_error``, call
             ``notify_status_change()``, log ERROR.

        Args:
            payload: Standard DAG payload dictionary forwarded from an
                upstream node.  Expected keys: ``points``, ``timestamp``,
                ``node_id``.
        """
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
        """
        Return a standardised status update for StatusAggregator broadcasts.

        State machine (per api-spec.md § 1.3):

        +-----------------------------+---------------------+-----------+-----------+
        | Condition                   | operational_state   | value     | color     |
        +=============================+=====================+===========+===========+
        | ``self.last_error`` is set  | ERROR               | False     | "gray"    |
        +-----------------------------+---------------------+-----------+-----------+
        | ``last_input_at`` < 5 s ago | RUNNING             | True      | "blue"    |
        +-----------------------------+---------------------+-----------+-----------+
        | idle / never received input | RUNNING             | False     | "gray"    |
        +-----------------------------+---------------------+-----------+-----------+

        Returns:
            :class:`~app.schemas.status.NodeStatusUpdate` describing the
            current node health and activity level.
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
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="processing",
                value=recently_active,
                color="blue" if recently_active else "gray",
            ),
        )
