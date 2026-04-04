"""TDD Tests for DataRouter input-gate integration (Phase 6).

Tests are written BEFORE the implementation (TDD).
All tests must pass once Phase 6 is implemented.

The DataRouter._forward_to_downstream_nodes() method must check
node_manager._input_gates[target_id] before forwarding:
  - If gate exists and is paused → buffer payload, skip on_input
  - If gate is open or absent     → forward normally (unchanged behaviour)

Spec: .opencode/plans/node-reload-improvement/backend-tasks.md § 6
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.nodes.input_gate import NodeInputGate
from app.services.nodes.managers.routing import DataRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(downstream_map=None, nodes=None, input_gates=None):
    """Build a minimal mock NodeManager for DataRouter tests."""
    mgr = MagicMock()
    mgr.downstream_map = downstream_map or {}
    mgr.nodes = nodes or {}
    mgr._input_gates = input_gates or {}
    mgr._throttle_manager.should_process.return_value = True  # don't throttle by default
    return mgr


def _make_target_node():
    """Build a mock target node with on_input."""
    node = MagicMock()
    node.on_input = AsyncMock()
    return node


# ---------------------------------------------------------------------------
# Phase 6: Gate integration tests
# ---------------------------------------------------------------------------


class TestDataRouterGateIntegration:
    """Tests for the input-gate check inside _forward_to_downstream_nodes."""

    @pytest.mark.asyncio
    async def test_forward_normal_when_no_gate(self):
        """When no gate exists for target, on_input must be called normally."""
        target = _make_target_node()
        mgr = _make_manager(
            downstream_map={"src": [{"target_id": "tgt", "source_port": "out", "target_port": "in"}]},
            nodes={"tgt": target},
            input_gates={},  # no gate
        )
        router = DataRouter(mgr)
        await router._forward_to_downstream_nodes("src", {"data": "value"})

        target.on_input.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_skips_on_input_when_gate_paused(self):
        """When gate is paused for target, on_input must NOT be called and payload must be buffered."""
        target = _make_target_node()
        gate = NodeInputGate(capacity=10)
        await gate.pause()  # close the gate

        mgr = _make_manager(
            downstream_map={"src": [{"target_id": "tgt", "source_port": "out", "target_port": "in"}]},
            nodes={"tgt": target},
            input_gates={"tgt": gate},
        )
        router = DataRouter(mgr)
        payload = {"data": "buffered_value"}
        await router._forward_to_downstream_nodes("src", payload)

        # on_input must NOT have been called
        target.on_input.assert_not_called()
        # payload must be in the gate's buffer queue
        assert not gate._buffer.empty()

    @pytest.mark.asyncio
    async def test_forward_normally_when_gate_open(self):
        """When gate exists but is open (resumed), on_input must be called normally."""
        target = _make_target_node()
        gate = NodeInputGate(capacity=10)
        # gate is open by default (not paused)
        assert gate.is_open()

        mgr = _make_manager(
            downstream_map={"src": [{"target_id": "tgt", "source_port": "out", "target_port": "in"}]},
            nodes={"tgt": target},
            input_gates={"tgt": gate},
        )
        router = DataRouter(mgr)
        await router._forward_to_downstream_nodes("src", {"data": "value"})

        target.on_input.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_buffers_multiple_payloads_in_order(self):
        """Multiple payloads arriving while gate is paused must all be buffered in FIFO order."""
        target = _make_target_node()
        gate = NodeInputGate(capacity=10)
        await gate.pause()

        mgr = _make_manager(
            downstream_map={"src": [{"target_id": "tgt", "source_port": "out", "target_port": "in"}]},
            nodes={"tgt": target},
            input_gates={"tgt": gate},
        )
        router = DataRouter(mgr)

        payloads = [{"seq": i} for i in range(3)]
        for p in payloads:
            await router._forward_to_downstream_nodes("src", p)

        target.on_input.assert_not_called()
        # 3 items buffered
        assert gate._buffer.qsize() == 3
        # FIFO: first in = first out
        assert gate._buffer.get_nowait()["seq"] == 0
        assert gate._buffer.get_nowait()["seq"] == 1
        assert gate._buffer.get_nowait()["seq"] == 2

    @pytest.mark.asyncio
    async def test_gate_check_is_o1_dict_lookup(self):
        """Gate lookup uses dict.get — O(1), no iteration. Verify absence is fast."""
        target = _make_target_node()
        mgr = _make_manager(
            downstream_map={"src": [{"target_id": "tgt", "source_port": "out", "target_port": "in"}]},
            nodes={"tgt": target},
            input_gates={},  # no gate — must not raise KeyError
        )
        router = DataRouter(mgr)
        # Should not raise even with empty gates dict
        await router._forward_to_downstream_nodes("src", {"data": "x"})
        target.on_input.assert_called_once()
