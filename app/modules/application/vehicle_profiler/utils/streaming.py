"""
ProfileStreamer — WebSocket streaming for partial profile point clouds.

Encapsulates the LIDR binary broadcast so that node.py stays focused on
DAG orchestration and state-machine logic.

Usage:
    streamer = ProfileStreamer(node_id="vp-001", enabled=True)
    await streamer.broadcast(points, timestamp)
"""
import asyncio
from typing import Optional

import numpy as np

from app.core.logging import get_logger
from app.services.shared.binary import pack_points_binary
from app.services.websocket.manager import manager as ws_manager

logger = get_logger(__name__)


class ProfileStreamer:
    """Streams partial profile point clouds to WebSocket subscribers.

    Only sends XYZ data (LIDR binary) for real-time frontend visualization.
    Does NOT forward to downstream DAG nodes — that is the node's job.

    Args:
        node_id:  Owning node ID (used to derive the WS topic).
        enabled:  Whether streaming is active.  When ``False``, all
                  ``broadcast()`` calls are no-ops.
    """

    def __init__(self, node_id: str, *, enabled: bool = False) -> None:
        self._node_id = node_id
        self._topic: str = f"profile_partial_streaming_{node_id[:8]}"
        self._enabled = enabled

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def topic(self) -> str:
        """WebSocket topic name for this streamer."""
        return self._topic

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def broadcast(self, points: np.ndarray, timestamp: float) -> None:
        """Pack *points* into LIDR binary and broadcast to WS subscribers.

        No-op when disabled or when nobody is subscribed to the topic.
        """
        if not self._enabled:
            return
        if not ws_manager.has_subscribers(self._topic):
            return
        try:
            binary = await asyncio.to_thread(pack_points_binary, points, timestamp)
            await ws_manager.broadcast(self._topic, binary)
        except Exception as e:
            logger.warning(f"[{self._node_id}] WS broadcast failed: {e}")
