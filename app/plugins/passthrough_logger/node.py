"""
Node implementation for the passthrough_logger plugin.

Receives a point-cloud payload, logs basic stats, then forwards it
downstream unchanged.  Demonstrates the minimal ModuleNode contract.
"""
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.schemas.status import NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode

logger = get_logger(__name__)


class PassthroughLoggerNode(ModuleNode):
    """Forwards point-cloud data unchanged and logs per-frame stats."""

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        log_every_n: int = 1,
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name
        self.log_every_n = max(1, log_every_n)

        self._frame_count: int = 0
        self._enabled: bool = False
        self._ws_topic: Optional[str] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def enable(self) -> None:
        self._enabled = True
        logger.info(f"[{self.name}] enabled")

    def disable(self) -> None:
        self._enabled = False
        logger.info(f"[{self.name}] disabled")

    # ── Data path ──────────────────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        if not self._enabled:
            return

        self._frame_count += 1

        if self._frame_count % self.log_every_n == 0:
            pts = payload.get("points")
            n_pts = len(pts) if pts is not None else 0
            logger.info(
                f"[{self.name}] frame={self._frame_count}  points={n_pts}"
            )

        # Broadcast to WebSocket subscribers (if visible)
        if self._ws_topic:
            try:
                from app.services.websocket.manager import manager as ws
                import numpy as np

                pts = payload.get("points")
                if pts is not None and len(pts):
                    await ws.broadcast(self._ws_topic, {
                        "node_id": self.id,
                        "points": pts.tolist() if hasattr(pts, "tolist") else pts,
                        "timestamp": payload.get("timestamp"),
                    })
            except Exception as exc:
                logger.debug(f"[{self.name}] WS broadcast skipped: {exc}")

        # Forward payload downstream unchanged
        await self.manager.forward_data(self.id, payload)

    # ── Status ─────────────────────────────────────────────────────────────

    def emit_status(self) -> NodeStatusUpdate:
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=(
                OperationalState.RUNNING if self._enabled else OperationalState.STOPPED
            ),
            application_state={
                "label": "frames_processed",
                "value": str(self._frame_count),
                "color": "green" if self._enabled else "grey",
            },
        )
