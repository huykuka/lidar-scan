"""
Unit tests for SnapshotNode - TDD phase, written before implementation.

Tests on_input caching, trigger_snapshot guard logic, emit_status state table,
and WebSocket invisibility per technical.md §3.
"""
import time
import pytest
from unittest.mock import AsyncMock, Mock, patch

# SnapshotNode will be importable once node.py is created
from app.modules.flow_control.snapshot.node import SnapshotNode
from app.schemas.status import OperationalState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(throttle_ms: float = 0, node_id: str = "snap-1") -> tuple[SnapshotNode, Mock]:
    """Return (node, mock_manager) with forward_data as AsyncMock."""
    manager = Mock()
    manager.forward_data = AsyncMock()
    node = SnapshotNode(
        manager=manager,
        node_id=node_id,
        name="Test Snapshot",
        throttle_ms=throttle_ms,
    )
    return node, manager


# ---------------------------------------------------------------------------
# TestSnapshotNodeInit
# ---------------------------------------------------------------------------

class TestSnapshotNodeInit:
    """Verify initial state after construction."""

    def test_ws_topic_is_none(self):
        """_ws_topic must be None — node is invisible (no WebSocket topic)."""
        node, _ = _make_node()
        assert node._ws_topic is None

    def test_latest_payload_is_none(self):
        node, _ = _make_node()
        assert node._latest_payload is None

    def test_is_processing_is_false(self):
        node, _ = _make_node()
        assert node._is_processing is False

    def test_snapshot_count_is_zero(self):
        node, _ = _make_node()
        assert node._snapshot_count == 0

    def test_error_count_is_zero(self):
        node, _ = _make_node()
        assert node._error_count == 0

    def test_last_error_is_none(self):
        node, _ = _make_node()
        assert node._last_error is None

    def test_last_trigger_at_is_none(self):
        node, _ = _make_node()
        assert node._last_trigger_at is None

    def test_id_set_correctly(self):
        node, _ = _make_node(node_id="my-snap")
        assert node.id == "my-snap"

    def test_throttle_ms_stored(self):
        node, _ = _make_node(throttle_ms=250)
        assert node.throttle_ms == 250


# ---------------------------------------------------------------------------
# TestSnapshotNodeOnInput
# ---------------------------------------------------------------------------

class TestSnapshotNodeOnInput:
    """on_input must cache payload and do nothing else."""

    @pytest.mark.asyncio
    async def test_on_input_stores_payload(self):
        node, manager = _make_node()
        payload = {"points": [1, 2, 3], "timestamp": 1.0}
        await node.on_input(payload)
        assert node._latest_payload is payload

    @pytest.mark.asyncio
    async def test_on_input_overwrites_previous(self):
        node, _ = _make_node()
        first = {"points": [1], "timestamp": 1.0}
        second = {"points": [2, 3], "timestamp": 2.0}
        await node.on_input(first)
        await node.on_input(second)
        assert node._latest_payload is second

    @pytest.mark.asyncio
    async def test_on_input_does_not_call_forward_data(self):
        node, manager = _make_node()
        await node.on_input({"points": [], "timestamp": 0.0})
        manager.forward_data.assert_not_called()


# ---------------------------------------------------------------------------
# TestSnapshotNodeTrigger — success path
# ---------------------------------------------------------------------------

class TestSnapshotNodeTriggerSuccess:
    """trigger_snapshot() happy path."""

    @pytest.mark.asyncio
    async def test_trigger_calls_forward_data_with_node_id(self):
        node, manager = _make_node()
        payload = {"points": [1, 2], "timestamp": 1.0}
        await node.on_input(payload)
        await node.trigger_snapshot()
        manager.forward_data.assert_called_once()
        call_args = manager.forward_data.call_args
        assert call_args[0][0] == "snap-1"

    @pytest.mark.asyncio
    async def test_trigger_forwards_shallow_copy(self):
        """forward_data receives a shallow copy, not the original object."""
        node, manager = _make_node()
        payload = {"points": [1, 2], "timestamp": 1.0}
        await node.on_input(payload)
        await node.trigger_snapshot()
        forwarded = manager.forward_data.call_args[0][1]
        # Different dict object
        assert forwarded is not payload
        # Same contents
        assert forwarded["points"] is payload["points"]  # shallow — array ref shared

    @pytest.mark.asyncio
    async def test_trigger_increments_snapshot_count(self):
        node, _ = _make_node()
        await node.on_input({"points": [], "timestamp": 0.0})
        await node.trigger_snapshot()
        assert node._snapshot_count == 1

    @pytest.mark.asyncio
    async def test_trigger_increments_snapshot_count_multiple_times(self):
        node, _ = _make_node()
        await node.on_input({"points": [], "timestamp": 0.0})
        await node.trigger_snapshot()
        await node.trigger_snapshot()
        await node.trigger_snapshot()
        assert node._snapshot_count == 3

    @pytest.mark.asyncio
    async def test_trigger_sets_last_trigger_at(self):
        node, _ = _make_node()
        before = time.time()
        await node.on_input({"points": [], "timestamp": 0.0})
        await node.trigger_snapshot()
        assert node._last_trigger_at is not None
        assert node._last_trigger_at >= before

    @pytest.mark.asyncio
    async def test_is_processing_cleared_after_success(self):
        node, _ = _make_node()
        await node.on_input({"points": [], "timestamp": 0.0})
        await node.trigger_snapshot()
        assert node._is_processing is False

    @pytest.mark.asyncio
    async def test_last_error_cleared_after_success(self):
        node, _ = _make_node()
        node._last_error = "previous error"
        await node.on_input({"points": [], "timestamp": 0.0})
        await node.trigger_snapshot()
        assert node._last_error is None

    @pytest.mark.asyncio
    @patch("app.modules.flow_control.snapshot.node.notify_status_change")
    async def test_trigger_calls_notify_status_change(self, mock_notify):
        node, _ = _make_node()
        await node.on_input({"points": [], "timestamp": 0.0})
        await node.trigger_snapshot()
        mock_notify.assert_called_once_with("snap-1")


# ---------------------------------------------------------------------------
# TestSnapshotNodeTrigger — error guards
# ---------------------------------------------------------------------------

class TestSnapshotNodeTriggerGuards:
    """All HTTPException guard conditions."""

    @pytest.mark.asyncio
    async def test_trigger_before_on_input_raises_404(self):
        from fastapi import HTTPException
        node, _ = _make_node()
        assert node._latest_payload is None
        with pytest.raises(HTTPException) as exc_info:
            await node.trigger_snapshot()
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_concurrent_trigger_raises_409(self):
        from fastapi import HTTPException
        node, _ = _make_node()
        await node.on_input({"points": [], "timestamp": 0.0})
        node._is_processing = True  # simulate in-flight trigger
        with pytest.raises(HTTPException) as exc_info:
            await node.trigger_snapshot()
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_throttle_window_raises_429(self):
        from fastapi import HTTPException
        node, _ = _make_node(throttle_ms=500)  # 500ms throttle
        await node.on_input({"points": [], "timestamp": 0.0})
        # Simulate a trigger that just happened (0.1s ago, within 500ms)
        node._last_trigger_time = time.time() - 0.1
        with pytest.raises(HTTPException) as exc_info:
            await node.trigger_snapshot()
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_throttle_zero_never_raises_429(self):
        """throttle_ms=0 means no throttle — should never raise 429."""
        node, _ = _make_node(throttle_ms=0)
        await node.on_input({"points": [], "timestamp": 0.0})
        node._last_trigger_time = time.time()  # just now
        # Should not raise
        await node.trigger_snapshot()

    @pytest.mark.asyncio
    async def test_throttle_expired_does_not_raise_429(self):
        """After throttle window has passed, trigger should succeed."""
        node, _ = _make_node(throttle_ms=100)  # 100ms throttle
        await node.on_input({"points": [], "timestamp": 0.0})
        # Simulate trigger that happened 200ms ago (outside window)
        node._last_trigger_time = time.time() - 0.2
        # Should not raise
        await node.trigger_snapshot()

    @pytest.mark.asyncio
    async def test_forward_data_exception_raises_500(self):
        from fastapi import HTTPException
        node, manager = _make_node()
        manager.forward_data = AsyncMock(side_effect=RuntimeError("downstream crash"))
        await node.on_input({"points": [], "timestamp": 0.0})
        with pytest.raises(HTTPException) as exc_info:
            await node.trigger_snapshot()
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_forward_data_exception_sets_last_error(self):
        node, manager = _make_node()
        manager.forward_data = AsyncMock(side_effect=RuntimeError("downstream crash"))
        await node.on_input({"points": [], "timestamp": 0.0})
        try:
            await node.trigger_snapshot()
        except Exception:
            pass
        assert node._last_error is not None
        assert "downstream crash" in node._last_error

    @pytest.mark.asyncio
    async def test_forward_data_exception_increments_error_count(self):
        node, manager = _make_node()
        manager.forward_data = AsyncMock(side_effect=RuntimeError("boom"))
        await node.on_input({"points": [], "timestamp": 0.0})
        try:
            await node.trigger_snapshot()
        except Exception:
            pass
        assert node._error_count == 1

    @pytest.mark.asyncio
    async def test_is_processing_cleared_after_error(self):
        """_is_processing MUST be reset to False even when forward_data raises."""
        node, manager = _make_node()
        manager.forward_data = AsyncMock(side_effect=RuntimeError("boom"))
        await node.on_input({"points": [], "timestamp": 0.0})
        try:
            await node.trigger_snapshot()
        except Exception:
            pass
        assert node._is_processing is False

    @pytest.mark.asyncio
    @patch("app.modules.flow_control.snapshot.node.notify_status_change")
    async def test_error_path_calls_notify_status_change(self, mock_notify):
        """notify_status_change is called even on error."""
        node, manager = _make_node()
        manager.forward_data = AsyncMock(side_effect=RuntimeError("boom"))
        await node.on_input({"points": [], "timestamp": 0.0})
        try:
            await node.trigger_snapshot()
        except Exception:
            pass
        mock_notify.assert_called_with("snap-1")


# ---------------------------------------------------------------------------
# TestSnapshotNodeEmitStatus
# ---------------------------------------------------------------------------

class TestSnapshotNodeEmitStatus:
    """emit_status() state table per technical.md §3.3."""

    def test_idle_state_running_gray(self):
        """No trigger yet: RUNNING, gray."""
        node, _ = _make_node()
        status = node.emit_status()
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is not None
        assert status.application_state.color == "gray"
        assert status.application_state.label == "snapshot"

    def test_recent_trigger_running_blue(self):
        """Triggered < 5 s ago: RUNNING, blue, value=count."""
        node, _ = _make_node()
        node._snapshot_count = 7
        node._last_trigger_at = time.time() - 1.0  # 1 second ago
        status = node.emit_status()
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is not None
        assert status.application_state.color == "blue"
        assert status.application_state.value == 7
        assert status.application_state.label == "snapshot"

    def test_old_trigger_running_gray(self):
        """Triggered > 5 s ago: RUNNING, gray."""
        node, _ = _make_node()
        node._snapshot_count = 3
        node._last_trigger_at = time.time() - 10.0  # 10 seconds ago
        status = node.emit_status()
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state.color == "gray"

    def test_error_state(self):
        """_last_error set: ERROR, red."""
        node, _ = _make_node()
        node._last_error = "something went wrong"
        status = node.emit_status()
        assert status.operational_state == OperationalState.ERROR
        assert status.application_state is not None
        assert status.application_state.color == "red"

    def test_error_state_never_running(self):
        node, _ = _make_node()
        node._last_error = "err"
        status = node.emit_status()
        assert status.operational_state != OperationalState.RUNNING

    def test_operational_state_never_stopped_or_initialize(self):
        """emit_status should never return STOPPED or INITIALIZE."""
        node, _ = _make_node()
        for state in [OperationalState.STOPPED, OperationalState.INITIALIZE]:
            status = node.emit_status()
            assert status.operational_state != state

    def test_node_id_in_status(self):
        node, _ = _make_node(node_id="snap-xyz")
        status = node.emit_status()
        assert status.node_id == "snap-xyz"
