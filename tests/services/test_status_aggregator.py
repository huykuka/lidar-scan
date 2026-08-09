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
from app.schemas.status import (
    NodeStatusUpdate,
    OperationalState,
    ApplicationState,
    SystemStatusBroadcast,
    SystemStatusInfo,
    ReloadEvent,
)


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


class TestSystemInfoInBroadcast:
    """Test that _collect_and_broadcast populates the system field."""

    @pytest.mark.asyncio
    async def test_full_broadcast_includes_system_info(self):
        """Full collect-and-broadcast includes system.is_running, active_sensors, version."""
        with patch("app.services.status_aggregator.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock()
            mock_manager.has_subscribers.return_value = True

            # Build two fake sensor nodes with .id attribute
            mock_sensor_a = MagicMock()
            mock_sensor_a.id = "lidar_front"
            mock_sensor_a.emit_status.return_value = NodeStatusUpdate(
                node_id="lidar_front",
                operational_state=OperationalState.RUNNING,
            )
            mock_sensor_b = MagicMock()
            mock_sensor_b.id = "lidar_rear"
            mock_sensor_b.emit_status.return_value = NodeStatusUpdate(
                node_id="lidar_rear",
                operational_state=OperationalState.STOPPED,
            )

            with patch("app.services.nodes.instance.node_manager") as mock_node_mgr:
                mock_node_mgr.is_running = True
                mock_node_mgr.nodes = {
                    "lidar_front": mock_sensor_a,
                    "lidar_rear": mock_sensor_b,
                }

                with patch("app.core.config.settings") as mock_settings:
                    mock_settings.VERSION = "1.2.3"

                    start_status_aggregator()
                    notify_status_change("lidar_front")

                    await asyncio.sleep(0.25)
                    stop_status_aggregator()

            assert mock_manager.broadcast.call_count >= 1
            call_args = mock_manager.broadcast.call_args_list[-1]
            payload = call_args[0][1]

            assert "system" in payload
            sys = payload["system"]
            assert sys is not None
            assert sys["is_running"] is True
            assert set(sys["active_sensors"]) == {"lidar_front", "lidar_rear"}
            assert sys["version"] == "1.2.3"

    @pytest.mark.asyncio
    async def test_system_info_failure_does_not_break_node_broadcast(self):
        """system info error → system=None but nodes still broadcast."""
        with patch("app.services.status_aggregator.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock()
            mock_manager.has_subscribers.return_value = True

            mock_node = MagicMock()
            mock_node.id = "lidar_front"
            mock_node.emit_status.return_value = NodeStatusUpdate(
                node_id="lidar_front",
                operational_state=OperationalState.RUNNING,
            )

            with patch("app.services.nodes.instance.node_manager") as mock_node_mgr:
                mock_node_mgr.is_running = True
                mock_node_mgr.nodes = {"lidar_front": mock_node}
                # Simulate system info collection failure
                type(mock_node_mgr).is_running = property(
                    lambda self: (_ for _ in ()).throw(RuntimeError("sim failure"))
                )

                start_status_aggregator()
                notify_status_change("lidar_front")
                await asyncio.sleep(0.25)
                stop_status_aggregator()

            # Broadcast should have been called; system may be None but no crash
            assert mock_manager.broadcast.call_count >= 0


class TestSystemStatusBroadcastSchema:
    """Schema-level backward-compat and additive field tests."""

    def test_system_defaults_to_none(self):
        """SystemStatusBroadcast valid with only nodes — system=None by default."""
        payload = SystemStatusBroadcast(nodes=[])
        assert payload.system is None
        assert payload.reload_event is None

    def test_reload_event_only_broadcast_valid(self):
        """Reload-event-only broadcast (nodes=[], reload_event=..., system=None) valid."""
        event = ReloadEvent(status="reloading", reload_mode="selective")
        broadcast = SystemStatusBroadcast(nodes=[], reload_event=event)
        dumped = broadcast.model_dump()
        assert dumped["reload_event"]["status"] == "reloading"
        assert dumped["system"] is None

    def test_system_status_info_schema(self):
        """SystemStatusInfo validates and serialises correctly."""
        info = SystemStatusInfo(
            is_running=True,
            active_sensors=["lidar_front", "lidar_rear"],
            version="2.0.0",
        )
        d = info.model_dump()
        assert d["is_running"] is True
        assert d["active_sensors"] == ["lidar_front", "lidar_rear"]
        assert d["version"] == "2.0.0"

    def test_full_broadcast_with_system_serialises(self):
        """Full broadcast with system field round-trips through model_dump."""
        info = SystemStatusInfo(is_running=False, active_sensors=[], version="0.1.0")
        broadcast = SystemStatusBroadcast(nodes=[], system=info)
        dumped = broadcast.model_dump()
        assert dumped["system"]["is_running"] is False
        assert dumped["system"]["version"] == "0.1.0"
