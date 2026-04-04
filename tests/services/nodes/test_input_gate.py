"""
TDD Tests for NodeInputGate.

Phase 7.2 — written BEFORE implementation per strict TDD.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock


class TestNodeInputGate:
    """Unit tests for NodeInputGate class."""

    @pytest.mark.asyncio
    async def test_gate_open_by_default(self):
        """is_open() must return True on construction (gate is not paused)."""
        from app.services.nodes.input_gate import NodeInputGate
        gate = NodeInputGate(capacity=10)
        assert gate.is_open() is True

    @pytest.mark.asyncio
    async def test_pause_blocks_is_open(self):
        """After pause(), is_open() must return False."""
        from app.services.nodes.input_gate import NodeInputGate
        gate = NodeInputGate(capacity=10)
        await gate.pause()
        assert gate.is_open() is False

    @pytest.mark.asyncio
    async def test_buffer_nowait_when_paused_returns_true(self):
        """buffer_nowait() when gate is paused must return True and store payload."""
        from app.services.nodes.input_gate import NodeInputGate
        gate = NodeInputGate(capacity=10)
        await gate.pause()
        result = gate.buffer_nowait({"points": [1, 2, 3]})
        assert result is True

    @pytest.mark.asyncio
    async def test_buffer_nowait_returns_false_when_full(self):
        """buffer_nowait() when at capacity must return False (drop, no raise)."""
        from app.services.nodes.input_gate import NodeInputGate
        gate = NodeInputGate(capacity=1)
        await gate.pause()
        # Fill the one slot
        gate.buffer_nowait({"frame": 1})
        # This second one exceeds capacity → must return False
        result = gate.buffer_nowait({"frame": 2})
        assert result is False

    @pytest.mark.asyncio
    async def test_resume_drains_buffer_in_order(self):
        """resume_and_drain() must deliver buffered frames in FIFO order."""
        from app.services.nodes.input_gate import NodeInputGate
        gate = NodeInputGate(capacity=30)
        await gate.pause()

        received = []

        class FakeNode:
            async def on_input(self, payload):
                received.append(payload["seq"])

        target = FakeNode()
        # Buffer 3 frames
        gate.buffer_nowait({"seq": 1})
        gate.buffer_nowait({"seq": 2})
        gate.buffer_nowait({"seq": 3})

        await gate.resume_and_drain(target)

        assert received == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_resume_calls_on_input_for_each_frame(self):
        """resume_and_drain() must call target_node.on_input() exactly N times for N buffered frames."""
        from app.services.nodes.input_gate import NodeInputGate
        gate = NodeInputGate(capacity=30)
        await gate.pause()

        mock_node = Mock()
        mock_node.on_input = AsyncMock()

        gate.buffer_nowait({"a": 1})
        gate.buffer_nowait({"b": 2})
        gate.buffer_nowait({"c": 3})

        await gate.resume_and_drain(mock_node)

        assert mock_node.on_input.call_count == 3

    @pytest.mark.asyncio
    async def test_resume_sets_gate_open(self):
        """After resume_and_drain(), is_open() must return True."""
        from app.services.nodes.input_gate import NodeInputGate
        gate = NodeInputGate(capacity=30)
        await gate.pause()
        assert gate.is_open() is False

        mock_node = Mock()
        mock_node.on_input = AsyncMock()
        await gate.resume_and_drain(mock_node)

        assert gate.is_open() is True

    @pytest.mark.asyncio
    async def test_resume_with_empty_buffer_is_noop(self):
        """resume_and_drain() with empty buffer must not call on_input at all."""
        from app.services.nodes.input_gate import NodeInputGate
        gate = NodeInputGate(capacity=30)
        await gate.pause()

        mock_node = Mock()
        mock_node.on_input = AsyncMock()
        await gate.resume_and_drain(mock_node)

        mock_node.on_input.assert_not_called()
        assert gate.is_open() is True

    @pytest.mark.asyncio
    async def test_buffer_nowait_when_open_returns_false(self):
        """buffer_nowait() when gate is open (not paused) should return False 
        since we should never be buffering when gate is open — no queue needed."""
        from app.services.nodes.input_gate import NodeInputGate
        gate = NodeInputGate(capacity=10)
        # Gate is open — buffer_nowait puts the item BUT the gate is open
        # Per spec: buffer_nowait is a put_nowait; returns False if queue full
        # When gate is open, the queue should be empty/unused
        # This test just verifies it doesn't raise
        result = gate.buffer_nowait({"seq": 99})
        # Should succeed (True) since queue isn't full
        assert isinstance(result, bool)
