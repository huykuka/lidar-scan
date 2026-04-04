"""
Input gate for buffering data during selective node reload.

Provides an asyncio.Event-based gate that pauses data flow to downstream
nodes while an upstream node is being reloaded. Data arriving during the
pause is buffered in a bounded asyncio.Queue and drained after the new
node instance starts.

Spec: .opencode/plans/node-reload-improvement/backend-tasks.md § 1.2
      .opencode/plans/node-reload-improvement/technical.md § 3.5
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class NodeInputGate:
    """asyncio.Event-based gate + bounded queue for pause/resume data flow.

    Lifecycle:
        1. Gate starts OPEN (``_gate`` event is *set*).
        2. ``pause()`` — clears event; subsequent calls to ``buffer_nowait()``
           enqueue payloads instead of allowing pass-through.
        3. ``resume_and_drain()`` — sets event again, then drains the queue
           by calling ``target_node.on_input(payload)`` for each buffered
           frame in FIFO order.

    The ``DataRouter._forward_to_downstream_nodes`` hot-path does an O(1)
    dict lookup for the gate.  When no reload is active, no gate exists for
    any node — essentially zero overhead.

    Args:
        capacity: Maximum number of frames to buffer when paused.
                  Frames beyond this limit are **dropped** with a DEBUG log.
                  Default: 30 frames (~500ms at 60 fps).
    """

    def __init__(self, capacity: int = 30) -> None:
        self._gate: asyncio.Event = asyncio.Event()
        self._gate.set()  # Initially open — data flows freely
        self._buffer: asyncio.Queue = asyncio.Queue(maxsize=capacity)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_open(self) -> bool:
        """Return True if the gate is open (data flows through normally)."""
        return self._gate.is_set()

    async def pause(self) -> None:
        """Close the gate; incoming frames will be buffered until resume."""
        self._gate.clear()

    async def resume_and_drain(self, target_node: Any) -> None:
        """Open the gate and deliver all buffered frames to *target_node*.

        Frames are delivered in FIFO order by calling
        ``await target_node.on_input(payload)`` for each frame.

        Args:
            target_node: The downstream node instance that receives buffered
                         frames. Must implement ``async on_input(payload)``.
        """
        # Open the gate first so new frames bypass buffering after this point
        self._gate.set()

        # Drain buffered frames in FIFO order
        while not self._buffer.empty():
            try:
                payload = self._buffer.get_nowait()
                await target_node.on_input(payload)
            except asyncio.QueueEmpty:
                break
            except Exception as exc:
                logger.error(
                    f"[NodeInputGate] Error delivering buffered frame to "
                    f"{target_node!r}: {exc}",
                    exc_info=True,
                )

    def buffer_nowait(self, payload: Any) -> bool:
        """Try to enqueue *payload* without blocking.

        Args:
            payload: Data frame to buffer.

        Returns:
            ``True`` if the frame was enqueued successfully.
            ``False`` if the queue is full (frame is dropped, with DEBUG log).
        """
        try:
            self._buffer.put_nowait(payload)
            return True
        except asyncio.QueueFull:
            logger.debug(
                "[NodeInputGate] Buffer full — dropping frame. "
                "Consider increasing gate capacity or reducing upstream throughput."
            )
            return False
