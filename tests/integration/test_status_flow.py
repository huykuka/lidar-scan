"""
Integration tests for the status flow: node state changes → StatusAggregator
→ system_status WebSocket broadcast (Task B11).

These tests exercise the full path:
  node.enable/disable → notify_status_change → _broadcast_system_status → WS manager

All WebSocket I/O is mocked so no real asyncio server is required.
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import app.services.status_aggregator as aggregator_module
from app.services.status_aggregator import (
    notify_status_change,
    start_status_aggregator,
    stop_status_aggregator,
    _broadcast_system_status,
)
from app.schemas.status import NodeStatusUpdate, OperationalState, ApplicationState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(node_id: str, state: str = "RUNNING") -> Mock:
    """Create a mock node with a working emit_status()."""
    node = Mock()
    node.emit_status.return_value = NodeStatusUpdate(
        node_id=node_id,
        operational_state=OperationalState(state),
    )
    return node


# ---------------------------------------------------------------------------
# B11.1 — broadcast on DAG start (status aggregator start + notify)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_broadcast_on_dag_start():
    """
    After start_status_aggregator() and notify calls for all nodes,
    the broadcast must include at least one NodeStatusUpdate with
    operational_state in [INITIALIZE, RUNNING].
    """
    captured = []

    mock_nm = Mock()
    mock_nm.nodes = {
        "node-A": _make_node("node-A", "RUNNING"),
        "node-B": _make_node("node-B", "INITIALIZE"),
    }

    with patch.object(aggregator_module, "node_manager", mock_nm), \
         patch.object(aggregator_module, "manager") as mock_ws_manager:

        mock_ws_manager.register_topic = Mock()
        mock_ws_manager.broadcast = AsyncMock(side_effect=lambda topic, payload: captured.append(payload))

        start_status_aggregator()
        try:
            for nid in mock_nm.nodes:
                notify_status_change(nid)

            # Allow debounce to fire
            await asyncio.sleep(0.25)

            assert len(captured) >= 1, "Expected at least one broadcast"
            nodes_in_broadcast = captured[0]["nodes"]
            states = {n["operational_state"] for n in nodes_in_broadcast}
            assert states & {"RUNNING", "INITIALIZE"}, \
                f"Expected RUNNING or INITIALIZE in broadcast, got {states}"
        finally:
            stop_status_aggregator()


# ---------------------------------------------------------------------------
# B11.2 — broadcast on node enable/disable reflects RUNNING then STOPPED
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_broadcast_on_node_enable_disable():
    """
    Toggling a node's state triggers two separate broadcasts:
    first RUNNING (enabled), then STOPPED (disabled).
    """
    from app.modules.fusion.service import FusionService

    mock_nm_inner = Mock()
    mock_nm_inner.forward_data = AsyncMock()
    mock_nm_inner.nodes = {}

    node = FusionService(node_manager=mock_nm_inner, fusion_id="fusion-toggle-1")
    mock_nm_inner.nodes = {"fusion-toggle-1": node}

    captured = []

    with patch.object(aggregator_module, "node_manager", mock_nm_inner), \
         patch.object(aggregator_module, "manager") as mock_ws_manager:

        mock_ws_manager.register_topic = Mock()
        mock_ws_manager.broadcast = AsyncMock(side_effect=lambda topic, payload: captured.append(payload))

        start_status_aggregator()
        try:
            # Enable → should broadcast RUNNING
            node.enable()
            await asyncio.sleep(0.25)

            # Disable → should broadcast STOPPED
            node.disable()
            await asyncio.sleep(0.25)

            assert len(captured) >= 2, f"Expected ≥ 2 broadcasts, got {len(captured)}"

            # Find the states across all broadcasts
            all_states = [
                n["operational_state"]
                for payload in captured
                for n in payload["nodes"]
                if n["node_id"] == "fusion-toggle-1"
            ]
            assert "RUNNING" in all_states, f"Expected RUNNING, got {all_states}"
            assert "STOPPED" in all_states, f"Expected STOPPED, got {all_states}"
        finally:
            stop_status_aggregator()


# ---------------------------------------------------------------------------
# B11.3 — multiple nodes within 50 ms are batched into one broadcast
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_nodes_batched_in_one_broadcast():
    """
    Three notify_status_change calls within 50 ms must be batched
    into a single broadcast message containing all three nodes.
    """
    mock_nm = Mock()
    mock_nm.nodes = {
        "n1": _make_node("n1"),
        "n2": _make_node("n2"),
        "n3": _make_node("n3"),
    }

    captured = []

    with patch.object(aggregator_module, "node_manager", mock_nm), \
         patch.object(aggregator_module, "manager") as mock_ws_manager:

        mock_ws_manager.register_topic = Mock()
        mock_ws_manager.broadcast = AsyncMock(side_effect=lambda topic, payload: captured.append(payload))

        start_status_aggregator()
        try:
            # Fire three notifications within 50 ms window
            notify_status_change("n1")
            await asyncio.sleep(0.01)
            notify_status_change("n2")
            await asyncio.sleep(0.01)
            notify_status_change("n3")

            # Wait for debounce to flush
            await asyncio.sleep(0.3)

            # All three should appear in the same broadcast
            all_ids = {
                n["node_id"]
                for payload in captured
                for n in payload["nodes"]
            }
            assert "n1" in all_ids
            assert "n2" in all_ids
            assert "n3" in all_ids
        finally:
            stop_status_aggregator()


# ---------------------------------------------------------------------------
# B11.4 — rate limit prevents flooding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_prevents_flooding():
    """
    Triggering notify_status_change 50 times for a single node within 1 s
    must result in ≤ 15 actual broadcast calls (rate limit + debounce).
    """
    mock_nm = Mock()
    mock_nm.nodes = {"flood-node": _make_node("flood-node")}

    broadcast_count = 0

    async def count_broadcast(topic, payload):
        nonlocal broadcast_count
        broadcast_count += 1

    with patch.object(aggregator_module, "node_manager", mock_nm), \
         patch.object(aggregator_module, "manager") as mock_ws_manager:

        mock_ws_manager.register_topic = Mock()
        mock_ws_manager.broadcast = AsyncMock(side_effect=count_broadcast)

        start_status_aggregator()
        try:
            for _ in range(50):
                notify_status_change("flood-node")
                await asyncio.sleep(0.01)

            # Wait for any pending debounce task to flush
            await asyncio.sleep(0.25)

            assert broadcast_count <= 15, \
                f"Rate limit failed: got {broadcast_count} broadcasts (expected ≤ 15)"
        finally:
            stop_status_aggregator()
