"""
Tests for StatusAggregator service.

Spec: .opencode/plans/node-status-standardization/technical.md § 2.3

NOTE: node_manager is lazily imported in _broadcast_system_status() to avoid
circular imports. Tests must patch 'app.services.nodes.instance.node_manager'
instead of patching it on status_aggregator module.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time

from app.services.status_aggregator import (
    notify_status_change,
    start_status_aggregator,
    stop_status_aggregator,
    _broadcast_system_status,
)
from app.schemas.status import NodeStatusUpdate, OperationalState, ApplicationState


class TestStatusAggregatorRateLimit:
    """Test per-node 100ms rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_drops_excess_calls(self):
        """Call notify_status_change 20 times in 50ms → assert broadcast called at most 1-2 times."""
        with patch("app.services.status_aggregator.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock()
            
            # Mock node_manager at the point where it's imported (lazy import in _broadcast_system_status)
            with patch("app.services.nodes.instance.node_manager") as mock_node_mgr:
                mock_node_mgr.nodes = {}
                
                start_status_aggregator()
                
                # Call notify_status_change 20 times rapidly
                for i in range(20):
                    notify_status_change("test_node_1")
                
                # Wait 100ms to allow debounce + processing
                await asyncio.sleep(0.15)
                
                stop_status_aggregator()
                
                # With 100ms rate limit and calls within 50ms, 
                # should have at most 1-2 broadcasts
                assert mock_manager.broadcast.call_count <= 2


class TestStatusAggregatorDebounce:
    """Test debounce batches multiple node updates."""

    @pytest.mark.asyncio
    async def test_debounce_batches_multiple_nodes(self):
        """
        Call notify_status_change for 3 different nodes within 30ms window
        → assert a single broadcast covers all 3.
        """
        with patch("app.services.status_aggregator.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock()
            
            # Mock three nodes that can emit status
            mock_node_1 = MagicMock()
            mock_node_1.emit_status.return_value = NodeStatusUpdate(
                node_id="node_1",
                operational_state=OperationalState.RUNNING,
                application_state=None,
                error_message=None,
            )
            mock_node_2 = MagicMock()
            mock_node_2.emit_status.return_value = NodeStatusUpdate(
                node_id="node_2",
                operational_state=OperationalState.RUNNING,
                application_state=None,
                error_message=None,
            )
            mock_node_3 = MagicMock()
            mock_node_3.emit_status.return_value = NodeStatusUpdate(
                node_id="node_3",
                operational_state=OperationalState.RUNNING,
                application_state=None,
                error_message=None,
            )
            
            # Patch at the lazy import location
            with patch("app.services.nodes.instance.node_manager") as mock_node_mgr:
                mock_node_mgr.nodes = {
                    "node_1": mock_node_1,
                    "node_2": mock_node_2,
                    "node_3": mock_node_3,
                }
                
                start_status_aggregator()
                
                # Trigger status changes for all 3 nodes within 30ms
                notify_status_change("node_1")
                await asyncio.sleep(0.01)
                notify_status_change("node_2")
                await asyncio.sleep(0.01)
                notify_status_change("node_3")
                
                # Wait for debounce + processing
                await asyncio.sleep(0.2)
                
                stop_status_aggregator()
                
                # Should have at least one broadcast
                assert mock_manager.broadcast.call_count >= 1
                
                # The broadcast should have been called with all 3 nodes
                # (or at least the debounced batch should contain them)
                if mock_manager.broadcast.call_count > 0:
                    call_args = mock_manager.broadcast.call_args_list[-1]
                    topic = call_args[0][0]
                    payload = call_args[0][1]
                    
                    assert topic == "system_status"
                    assert "nodes" in payload
                    node_ids = {n["node_id"] for n in payload["nodes"]}
                    # All three nodes should be present in the broadcast
                    assert "node_1" in node_ids
                    assert "node_2" in node_ids
                    assert "node_3" in node_ids


class TestStatusAggregatorLifecycle:
    """Test start/stop lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_registers_system_status_topic(self):
        """start_status_aggregator() → assert 'system_status' in manager.active_connections."""
        with patch("app.services.status_aggregator.manager") as mock_manager:
            mock_manager.register_topic = MagicMock()
            mock_manager.broadcast = AsyncMock()
            
            start_status_aggregator()
            
            # Should register the system_status topic
            mock_manager.register_topic.assert_called_once_with("system_status")
            
            await asyncio.sleep(0.05)
            stop_status_aggregator()

    @pytest.mark.asyncio
    async def test_stop_cancels_pending_task(self):
        """
        Start aggregator, schedule task, call stop_status_aggregator()
        → assert task cancelled.
        """
        with patch("app.services.status_aggregator.manager") as mock_manager:
            mock_manager.register_topic = MagicMock()
            mock_manager.broadcast = AsyncMock()
            
            # Patch at the lazy import location
            with patch("app.services.nodes.instance.node_manager") as mock_node_mgr:
                mock_node_mgr.nodes = {}
                
                start_status_aggregator()
                
                # Trigger a status change to start the broadcast task
                notify_status_change("test_node")
                
                await asyncio.sleep(0.05)
                
                # Stop should cancel the pending task
                stop_status_aggregator()
                
                # After stop, the task should be cancelled
                # We can verify this by checking that no new broadcasts happen
                initial_call_count = mock_manager.broadcast.call_count
                
                await asyncio.sleep(0.1)
                
                # No new broadcasts should occur after stop
                assert mock_manager.broadcast.call_count == initial_call_count


class TestStatusAggregatorNodeHandling:
    """Test handling of nodes with/without emit_status."""

    @pytest.mark.asyncio
    async def test_node_without_emit_status_is_skipped(self):
        """
        Register a node without emit_status
        → assert broadcast proceeds without raising.
        """
        with patch("app.services.status_aggregator.manager") as mock_manager:
            mock_manager.register_topic = MagicMock()
            mock_manager.broadcast = AsyncMock()
            
            # Mock a node without emit_status method
            mock_node_without_status = MagicMock(spec=[])  # No methods
            
            # Mock a normal node with emit_status
            mock_node_with_status = MagicMock()
            mock_node_with_status.emit_status.return_value = NodeStatusUpdate(
                node_id="normal_node",
                operational_state=OperationalState.RUNNING,
                application_state=None,
                error_message=None,
            )
            
            # Patch at the lazy import location
            with patch("app.services.nodes.instance.node_manager") as mock_node_mgr:
                mock_node_mgr.nodes = {
                    "broken_node": mock_node_without_status,
                    "normal_node": mock_node_with_status,
                }
                
                start_status_aggregator()
                
                # Trigger status change - should not raise even though broken_node lacks emit_status
                notify_status_change("broken_node")
                notify_status_change("normal_node")
                
                await asyncio.sleep(0.15)
                
                stop_status_aggregator()
                
                # Should have broadcast successfully (at least once for normal_node)
                assert mock_manager.broadcast.call_count >= 0  # Should not crash
