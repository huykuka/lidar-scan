"""Isolated NodeManager used for offline replay."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from app.services.nodes.orchestrator import NodeManager


class ReplayNodeManager(NodeManager):
    """NodeManager with a frame barrier.

    Several nodes (e.g. ``OperationNode``) hand their output on with a fire-and-forget
    ``asyncio.create_task(manager.forward_data(...))``.  In live operation that is fine,
    but a fast replay would emit the next frame while the previous one is still being
    processed, mis-attributing outputs and dropping frames through node back-pressure.

    ``forward_data`` is therefore a *plain* function: it bumps an in-flight counter when
    the call is made (before any task is created) and returns a coroutine that decrements
    it when done.  ``wait_idle`` lets the PlaybackNode block until a frame has fully
    propagated through the DAG, including every hop of fire-and-forget forwarding.
    """

    isolated = True

    def __init__(self) -> None:
        super().__init__()
        self._inflight = 0
        self._idle = asyncio.Event()
        self._idle.set()

    def forward_data(self, source_id: str, payload: Any, active_port: Optional[str] = None):  # type: ignore[override]
        self._inflight += 1
        self._idle.clear()
        return self._tracked_forward(source_id, payload, active_port)

    async def _tracked_forward(self, source_id: str, payload: Any, active_port: Optional[str]) -> None:
        try:
            await self._data_router.forward_data(source_id, payload, active_port=active_port)
        finally:
            self._inflight -= 1
            if self._inflight <= 0:
                self._inflight = 0
                self._idle.set()

    async def wait_idle(self, timeout: float = 60.0) -> None:
        """Wait until no forward_data call is in flight (bounded, to survive leaked counts)."""
        if self._idle.is_set():
            return
        try:
            await asyncio.wait_for(self._idle.wait(), timeout)
        except asyncio.TimeoutError:
            self._inflight = 0
            self._idle.set()
