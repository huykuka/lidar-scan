"""
Node implementation for _template.

Rename this class, update __init__ parameters, and implement on_input.

Required contract (validated by the plugin loader):
  • async def on_input(self, payload)   — called for every incoming frame
  • def emit_status(self) -> NodeStatusUpdate
  • def start(...) OR def enable()
"""
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.schemas.status import NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode

logger = get_logger(__name__)


class TemplateNode(ModuleNode):
    """TODO: replace with a real docstring describing what this node does."""

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        # ── TODO: add your config params here ─────────────────────────────
        my_string: str = "hello",
        my_number: float = 1.0,
        my_bool: bool = False,
        my_select: str = "fast",
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name

        # TODO: store config params
        self.my_string = my_string
        self.my_number = my_number
        self.my_bool = my_bool
        self.my_select = my_select

        # Internal state
        self._enabled: bool = False
        self._frame_count: int = 0
        self._ws_topic: Optional[str] = None   # set by NodeManager when visibility is on

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self, data_queue=None, runtime_status=None) -> None:
        """Called by the orchestrator's start_all_nodes(). Delegates to enable()."""
        self.enable()

    def enable(self) -> None:
        self._enabled = True
        logger.info(f"[{self.name}] enabled")

    def disable(self) -> None:
        self._enabled = False
        logger.info(f"[{self.name}] disabled")

    # ── Data path ──────────────────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """Receives a point-cloud payload dict.

        payload keys (all optional — always guard with .get()):
            "points"    – numpy ndarray shape (N, 3) or (N, 4+)
            "timestamp" – float Unix seconds
            "sensor_id" – str
            "metadata"  – dict of extra key/value pairs
        """
        if not self._enabled:
            return

        self._frame_count += 1

        # ── TODO: implement your processing logic here ─────────────────────
        points = payload.get("points")
        # e.g. filtered = my_filter(points, threshold=self.my_number)
        # payload["points"] = filtered   # mutate before forwarding

        # ── Optional: broadcast to WebSocket subscribers ───────────────────
        if self._ws_topic and points is not None:
            try:
                from app.services.websocket.manager import manager as ws
                await ws.broadcast(self._ws_topic, {
                    "node_id": self.id,
                    "points": points.tolist() if hasattr(points, "tolist") else points,
                    "timestamp": payload.get("timestamp"),
                })
            except Exception as exc:
                logger.debug(f"[{self.name}] WS broadcast skipped: {exc}")

        # ── Forward (possibly modified) payload downstream ─────────────────
        await self.manager.forward_data(self.id, payload)

    # ── Status ─────────────────────────────────────────────────────────────

    def emit_status(self) -> NodeStatusUpdate:
        """Polled by the orchestrator to report node health to the UI."""
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=(
                OperationalState.RUNNING if self._enabled else OperationalState.STOPPED
            ),
            application_state={
                # TODO: replace with a meaningful metric for your node
                "label": "frames_processed",
                "value": str(self._frame_count),
                "color": "green" if self._enabled else "grey",
            },
        )
