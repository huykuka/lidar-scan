"""
SnapshotNode — triggered passthrough gate for the DAG flow-control layer.

Acts as an in-memory cache of the most recent upstream payload.  Forwarding
is deliberately *not* triggered on every incoming frame; instead a caller must
invoke ``trigger_snapshot()`` explicitly (typically via the REST API).

Technical spec: .opencode/plans/snapshot-node/technical.md §3
"""
import time
from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)

# Seconds after a trigger during which emit_status reports "blue" (active).
_RECENT_TRIGGER_WINDOW_SEC: float = 5.0


class SnapshotNode(ModuleNode):
    """
    Flow-control node that caches the latest upstream payload and forwards it
    only when explicitly triggered via HTTP.

    Attributes:
        id: Node identifier.
        name: Display name.
        manager: NodeManager reference.
        throttle_ms: Minimum milliseconds between successful triggers (0 = off).
        _ws_topic: Always ``None`` — invisible node, no WebSocket topic.
        _latest_payload: Last payload received from upstream.
        _is_processing: Concurrency guard — ``True`` while forward_data is running.
        _last_trigger_time: ``time.time()`` of the last *successful* trigger start.
        _snapshot_count: Running count of successful snapshots.
        _last_trigger_at: ``time.time()`` of the last successful trigger completion.
        _last_error: Error message from the most recent failed trigger.
        _error_count: Running count of failed triggers.
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        throttle_ms: float = 0,
    ) -> None:
        """
        Initialise the SnapshotNode.

        Args:
            manager: NodeManager orchestrator reference.
            node_id: Unique node identifier.
            name: Display name.
            throttle_ms: Minimum ms between successful triggers (0 = no limit).
        """
        self.id: str = node_id
        self.name: str = name
        self.manager: Any = manager
        self.throttle_ms: float = throttle_ms

        # Invisible node — no WebSocket topic registration.
        self._ws_topic: Optional[str] = None

        # Mutable state
        self._latest_payload: Optional[Dict[str, Any]] = None
        self._is_processing: bool = False
        self._last_trigger_time: float = 0.0
        self._snapshot_count: int = 0
        self._last_trigger_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._error_count: int = 0

        logger.debug(f"Created SnapshotNode {node_id!r} (throttle_ms={throttle_ms})")

    # ------------------------------------------------------------------
    # ModuleNode interface
    # ------------------------------------------------------------------

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """
        Cache the latest upstream payload.

        This method is non-blocking and intentionally fast — it does *not*
        forward data downstream.  Forwarding only happens on an explicit
        ``trigger_snapshot()`` call.

        Args:
            payload: Upstream data frame.
        """
        self._latest_payload = payload
        logger.debug(f"SnapshotNode {self.id!r}: cached new payload")

    def emit_status(self) -> NodeStatusUpdate:
        """
        Return a standardised status update.

        State table (technical.md §3.3):

        | Condition                        | operational_state | color  |
        |----------------------------------|-------------------|--------|
        | ``_last_error`` set              | ERROR             | red    |
        | ``_last_trigger_at`` < 5 s ago   | RUNNING           | blue   |
        | idle (no trigger or > 5 s ago)   | RUNNING           | gray   |

        Returns:
            NodeStatusUpdate
        """
        if self._last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(
                    label="snapshot",
                    value="error",
                    color="red",
                ),
                error_message=self._last_error,
            )

        if (
            self._last_trigger_at is not None
            and time.time() - self._last_trigger_at < _RECENT_TRIGGER_WINDOW_SEC
        ):
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
                application_state=ApplicationState(
                    label="snapshot",
                    value=self._snapshot_count,
                    color="blue",
                ),
            )

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="snapshot",
                value=self._snapshot_count,
                color="gray",
            ),
        )

    # ------------------------------------------------------------------
    # Snapshot trigger (called by the API service layer)
    # ------------------------------------------------------------------

    async def trigger_snapshot(self) -> None:
        """
        Atomically snapshot the latest cached payload and forward it downstream.

        Guard order:
            1. ``_is_processing`` → HTTP 409 (drop concurrent trigger)
            2. ``throttle_ms`` window → HTTP 429 (drop throttled trigger)
            3. ``_latest_payload is None`` → HTTP 404 (no data yet)

        Raises:
            HTTPException(409): A prior trigger is still processing.
            HTTPException(429): Within the configured throttle window.
            HTTPException(404): No upstream data has been received yet.
            HTTPException(500): ``manager.forward_data`` raised an exception.
        """
        # ── Guard 1: concurrency ───────────────────────────────────────
        if self._is_processing:
            logger.warning(f"SnapshotNode {self.id!r}: concurrent trigger dropped (409)")
            raise HTTPException(
                status_code=409,
                detail="Trigger dropped: snapshot still processing",
            )

        # ── Guard 2: throttle ──────────────────────────────────────────
        if self.throttle_ms > 0:
            elapsed_ms = (time.time() - self._last_trigger_time) * 1000
            if elapsed_ms < self.throttle_ms:
                logger.warning(
                    f"SnapshotNode {self.id!r}: throttle guard active "
                    f"({elapsed_ms:.0f}ms < {self.throttle_ms}ms) → 429"
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Trigger dropped: throttle window active ({self.throttle_ms:.0f}ms)",
                )

        # ── Guard 3: no upstream data ──────────────────────────────────
        if self._latest_payload is None:
            logger.warning(f"SnapshotNode {self.id!r}: no upstream data available → 404")
            raise HTTPException(
                status_code=404,
                detail="No upstream data available",
            )

        # ── Execute snapshot ───────────────────────────────────────────
        self._is_processing = True
        try:
            snapshot: Dict[str, Any] = dict(self._latest_payload)
            await self.manager.forward_data(self.id, snapshot)

            # Update success counters
            self._snapshot_count += 1
            self._last_trigger_at = time.time()
            self._last_trigger_time = time.time()
            self._last_error = None

            logger.info(
                f"SnapshotNode {self.id!r}: snapshot #{self._snapshot_count} forwarded"
            )
            notify_status_change(self.id)

        except HTTPException:
            # Re-raise HTTP exceptions from guards without wrapping
            raise

        except Exception as exc:
            error_msg = str(exc)
            self._last_error = error_msg
            self._error_count += 1
            logger.error(
                f"SnapshotNode {self.id!r}: forwarding failed — {error_msg}",
                exc_info=True,
            )
            notify_status_change(self.id)
            raise HTTPException(
                status_code=500,
                detail=f"Snapshot forwarding failed: {error_msg}",
            )

        finally:
            self._is_processing = False
