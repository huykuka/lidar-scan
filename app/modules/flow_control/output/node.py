"""
OutputNode - Terminal sink DAG node that broadcasts metadata to WebSocket
and streams it over a configurable TCP server.

This node:
- Accepts one input connection (terminal — no downstream forwarding)
- Extracts JSON-serializable metadata from the incoming payload
- Broadcasts via the system_status WebSocket topic (type discriminator: output_node_metadata)
- Optionally streams over TCP (NDJSON) to all connected clients
"""
import asyncio
import time
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change
from .tcp_server import TcpStreamServer

logger = get_logger(__name__)


class OutputNode(ModuleNode):
    """
    Terminal sink node that broadcasts payload metadata on the system_status topic.

    Does NOT forward data downstream. Metadata is extracted by stripping
    binary/internal fields and coercing numpy scalars to Python native types.

    Attributes:
        id: Node identifier
        name: Display name
        manager: Reference to NodeManager orchestrator
        metadata_count: Total number of metadata messages processed
        error_count: Number of errors encountered
        last_metadata_at: Unix timestamp of most recent successful broadcast (or None)
    """

    def __init__(
            self,
            manager: Any,
            node_id: str,
            name: str,
            config: Dict[str, Any],
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name
        self._config = config
        self._tcp: Optional[TcpStreamServer] = TcpStreamServer.from_config(config)

        # Runtime counters
        self.metadata_count: int = 0
        self.error_count: int = 0
        self.last_metadata_at: Optional[float] = None

        if self._tcp is not None:
            asyncio.create_task(self._tcp.start())

        logger.debug(
            f"Created OutputNode {node_id} "
            f"(tcp={'enabled' if self._tcp else 'disabled'})"
        )

    async def on_input(self, payload: Dict[str, Any]) -> None:
        try:
            metadata = self._extract_metadata(payload)

            # CASE 1: metadata missing → DO NOTHING
            if metadata is None and "metadata" not in payload:
                return

            # CASE 2: metadata exists but empty dict → DO NOTHING
            if metadata == {}:
                return

            # CASE 3: metadata is None (explicit null) → SEND
            # CASE 4: metadata has data → SEND

            message: Dict[str, Any] = {
                "type": "output_node_metadata",
                "name": self.name,
                "node_id": self.id,
                "timestamp": payload.get("timestamp") or time.time(),
                "metadata": metadata,  # can be None or dict
            }

            from app.services.websocket.manager import manager as ws_manager

            asyncio.create_task(ws_manager.broadcast("output", message))

            if self._tcp is not None:
                asyncio.create_task(self._tcp.broadcast(message))

            self.last_metadata_at = time.time()
            self.metadata_count += 1
            notify_status_change(self.id)

        except Exception as e:
            self.error_count += 1
            logger.error(f"OutputNode {self.id}: on_input error: {e}", exc_info=True)
            notify_status_change(self.id)

    def _extract_metadata(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            if "metadata" not in payload:
                return None  # <-- missing → skip

            return payload["metadata"]  # can be None, {}, or dict

        except Exception as e:
            logger.error(f"OutputNode {self.id}: _extract_metadata failed: {e}", exc_info=True)
            return None

    def emit_status(self) -> NodeStatusUpdate:
        """
        Return standardised status for this Output Node.

        State mapping:
        - No data received yet → RUNNING, no application_state
        - Data received within last 5s → RUNNING, metadata=True (blue)
        - Data received but stale (>5s) → RUNNING, metadata=False (gray)
        """
        if self.last_metadata_at is None:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
            )

        recent = (time.time() - self.last_metadata_at) < 5.0
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="metadata",
                value=recent,
                color="blue" if recent else "gray",
            ),
        )

    async def stop(self) -> None:
        """Called by the orchestrator when the node is torn down.

        Declared async so the lifecycle manager awaits it, guaranteeing the
        TCP port is fully released before a replacement node tries to bind.
        """
        if self._tcp is not None:
            await self._tcp.stop_async()
            self._tcp = None
