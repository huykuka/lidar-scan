"""
Unit tests for the OutputNode DAG module.

Tests: metadata extraction, WebSocket broadcast, webhook delivery,
status reporting, and hot-reload webhook config.

TDD: Tests written before implementation to drive development.
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call

import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(config=None):
    """Create an OutputNode with a mock manager and optional config."""
    from app.modules.flow_control.output.node import OutputNode

    manager = Mock()
    manager.downstream_map = {}
    return OutputNode(
        manager=manager,
        node_id="out-node-1",
        name="Test Output",
        config=config or {},
    )


# ---------------------------------------------------------------------------
# B6.1 — OutputNode.on_input tests
# ---------------------------------------------------------------------------

class TestOutputNodeOnInput:
    """Tests for on_input: broadcast path and webhook path."""

    @pytest.mark.asyncio
    async def test_on_input_broadcasts_metadata(self):
        """on_input should call ws_manager.broadcast with type='output_node_metadata'."""
        node = _make_node()

        with patch(
            "app.modules.flow_control.output.node.asyncio.create_task"
        ) as mock_create_task, patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            # Mock ws_manager.broadcast at the module import level
            mock_broadcast = AsyncMock()
            with patch(
                "app.services.websocket.manager.manager.broadcast",
                mock_broadcast,
            ):
                payload = {"timestamp": 1700000000.0, "point_count": 1000, "points": []}
                await node.on_input(payload)

        # create_task should have been called at least once (for ws broadcast)
        assert mock_create_task.call_count >= 1

    @pytest.mark.asyncio
    async def test_on_input_message_has_correct_type_and_node_id(self):
        """The broadcast message must have type='output_node_metadata' and correct node_id."""
        node = _make_node()
        captured_messages = []

        async def fake_broadcast(topic, message):
            captured_messages.append((topic, message))

        with patch(
            "app.modules.flow_control.output.node.asyncio.create_task",
            side_effect=lambda coro: asyncio.ensure_future(coro),
        ), patch(
            "app.services.websocket.manager.manager.broadcast",
            side_effect=fake_broadcast,
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            payload = {"timestamp": 1700000000.0, "point_count": 5000, "points": []}
            await node.on_input(payload)

        # Allow tasks to run
        await asyncio.sleep(0)

        assert len(captured_messages) == 1
        topic, message = captured_messages[0]
        assert topic == "system_status"
        assert message["type"] == "output_node_metadata"
        assert message["node_id"] == "out-node-1"
        assert "metadata" in message
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_on_input_fires_webhook_when_enabled(self):
        """If webhook is configured, create_task should be called for webhook send too."""
        config = {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_auth_type": "none",
        }
        node = _make_node(config=config)
        assert node._webhook is not None, "Webhook should be initialized when enabled"

        send_mock = AsyncMock()
        node._webhook.send = send_mock  # type: ignore[assignment]

        with patch(
            "app.modules.flow_control.output.node.asyncio.create_task",
            side_effect=lambda coro: asyncio.ensure_future(coro),
        ), patch(
            "app.services.websocket.manager.manager.broadcast",
            new_callable=AsyncMock,
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            payload = {"timestamp": 1700000000.0, "point_count": 1000, "points": []}
            await node.on_input(payload)

        await asyncio.sleep(0)
        send_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_input_no_webhook_when_disabled(self):
        """With webhook disabled, _webhook is None and send is never called."""
        node = _make_node(config={"webhook_enabled": False})
        assert node._webhook is None

        with patch(
            "app.modules.flow_control.output.node.asyncio.create_task",
            side_effect=lambda coro: asyncio.ensure_future(coro),
        ), patch(
            "app.services.websocket.manager.manager.broadcast",
            new_callable=AsyncMock,
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            payload = {"timestamp": 1700000000.0, "points": []}
            # Should complete without error — just no webhook call
            await node.on_input(payload)

        await asyncio.sleep(0)
        # If we get here without exception, the test passes

    @pytest.mark.asyncio
    async def test_on_input_increments_metadata_count(self):
        """Each on_input call increments metadata_count."""
        node = _make_node()
        assert node.metadata_count == 0

        with patch(
            "app.modules.flow_control.output.node.asyncio.create_task"
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            for _ in range(3):
                await node.on_input({"points": [], "timestamp": 1.0})

        assert node.metadata_count == 3

    @pytest.mark.asyncio
    async def test_on_input_updates_last_metadata_at(self):
        """on_input updates last_metadata_at to approximately now."""
        node = _make_node()
        assert node.last_metadata_at is None

        before = time.time()
        with patch(
            "app.modules.flow_control.output.node.asyncio.create_task"
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            await node.on_input({"points": [], "timestamp": 1.0})
        after = time.time()

        assert node.last_metadata_at is not None
        assert before <= node.last_metadata_at <= after

    @pytest.mark.asyncio
    async def test_on_input_uses_payload_timestamp_when_present(self):
        """The broadcast message should carry the payload's timestamp, not time.time()."""
        node = _make_node()
        captured = []

        async def fake_broadcast(topic, message):
            captured.append(message)

        with patch(
            "app.modules.flow_control.output.node.asyncio.create_task",
            side_effect=lambda coro: asyncio.ensure_future(coro),
        ), patch(
            "app.services.websocket.manager.manager.broadcast",
            side_effect=fake_broadcast,
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            await node.on_input({"timestamp": 9999.5, "points": []})

        await asyncio.sleep(0)
        assert captured[0]["timestamp"] == 9999.5

    @pytest.mark.asyncio
    async def test_on_input_increments_error_count_on_exception(self):
        """If _extract_metadata raises, error_count is incremented and no exception propagates."""
        node = _make_node()

        with patch.object(
            node, "_extract_metadata", side_effect=RuntimeError("boom")
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            await node.on_input({"points": [], "timestamp": 1.0})

        assert node.error_count == 1
        assert node.metadata_count == 0  # Not incremented on error


# ---------------------------------------------------------------------------
# B6.1 — _extract_metadata tests
# ---------------------------------------------------------------------------

class TestExtractMetadata:
    """Tests for OutputNode._extract_metadata."""

    def test_extract_metadata_strips_points(self):
        """'points' key must be absent from the result."""
        node = _make_node()
        payload = {"points": np.zeros((100, 3)), "point_count": 100, "timestamp": 1.0}
        result = node._extract_metadata(payload)
        assert "points" not in result
        assert result["point_count"] == 100

    def test_extract_metadata_strips_node_id(self):
        """'node_id' key must be stripped from the result."""
        node = _make_node()
        payload = {"node_id": "upstream-1", "point_count": 50, "points": []}
        result = node._extract_metadata(payload)
        assert "node_id" not in result
        assert result["point_count"] == 50

    def test_extract_metadata_strips_processed_by(self):
        """'processed_by' key must be stripped from the result."""
        node = _make_node()
        payload = {"processed_by": "some_node", "intensity": 0.5, "points": []}
        result = node._extract_metadata(payload)
        assert "processed_by" not in result
        assert result["intensity"] == 0.5

    def test_extract_metadata_coerces_numpy_float(self):
        """numpy float32 scalar should become a plain Python float."""
        node = _make_node()
        np_val = np.float32(0.72)
        payload = {"intensity_avg": np_val, "points": []}
        result = node._extract_metadata(payload)
        assert isinstance(result["intensity_avg"], float)
        assert not isinstance(result["intensity_avg"], np.floating)
        assert abs(result["intensity_avg"] - 0.72) < 1e-4

    def test_extract_metadata_coerces_numpy_int(self):
        """numpy int64 scalar should become a plain Python int."""
        node = _make_node()
        np_val = np.int64(45000)
        payload = {"point_count": np_val, "points": []}
        result = node._extract_metadata(payload)
        assert isinstance(result["point_count"], int)
        assert not isinstance(result["point_count"], np.integer)
        assert result["point_count"] == 45000

    def test_extract_metadata_preserves_plain_python_types(self):
        """Plain Python str/int/float/bool values should pass through unchanged."""
        node = _make_node()
        payload = {
            "sensor_name": "lidar_front",
            "frame_id": "frame_001",
            "enabled": True,
            "processing_time_ms": 12.4,
            "points": [],
        }
        result = node._extract_metadata(payload)
        assert result["sensor_name"] == "lidar_front"
        assert result["frame_id"] == "frame_001"
        assert result["enabled"] is True
        assert result["processing_time_ms"] == 12.4

    def test_extract_metadata_empty_on_error(self):
        """If payload.items() raises, _extract_metadata should return {} without re-raising."""
        node = _make_node()
        bad_payload = MagicMock()
        bad_payload.items.side_effect = RuntimeError("iteration failed")
        result = node._extract_metadata(bad_payload)  # type: ignore[arg-type]
        assert result == {}

    def test_extract_metadata_no_extra_fields_returns_empty(self):
        """Payload with only excluded keys returns empty dict — valid, not an error."""
        node = _make_node()
        payload = {"points": np.zeros((10, 3)), "node_id": "src", "processed_by": "n1"}
        result = node._extract_metadata(payload)
        assert result == {}


# ---------------------------------------------------------------------------
# B6.1 — emit_status tests
# ---------------------------------------------------------------------------

class TestOutputNodeEmitStatus:
    """Tests for OutputNode.emit_status."""

    def test_emit_status_running_no_data(self):
        """Node with no data yet returns RUNNING, no application_state."""
        from app.schemas.status import OperationalState

        node = _make_node()
        status = node.emit_status()
        assert status.node_id == "out-node-1"
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is None

    def test_emit_status_running_recent_data(self):
        """Node with data received within 5s returns RUNNING, metadata=True, blue."""
        from app.schemas.status import OperationalState

        node = _make_node()
        node.last_metadata_at = time.time()  # Just now

        status = node.emit_status()
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is not None
        assert status.application_state.label == "metadata"
        assert status.application_state.value is True
        assert status.application_state.color == "blue"

    def test_emit_status_running_stale_data(self):
        """Node with data older than 5s returns RUNNING, metadata=False, gray."""
        from app.schemas.status import OperationalState

        node = _make_node()
        node.last_metadata_at = time.time() - 10.0  # 10 seconds ago

        status = node.emit_status()
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is not None
        assert status.application_state.label == "metadata"
        assert status.application_state.value is False
        assert status.application_state.color == "gray"


# ---------------------------------------------------------------------------
# B4.5 — _rebuild_webhook test
# ---------------------------------------------------------------------------

class TestRebuildWebhook:
    """Test hot-reload of webhook config."""

    def test_rebuild_webhook_creates_sender_when_enabled(self):
        """_rebuild_webhook with webhook_enabled=True creates a WebhookSender."""
        node = _make_node()
        assert node._webhook is None

        config = {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_auth_type": "none",
        }
        node._rebuild_webhook(config)
        assert node._webhook is not None

    def test_rebuild_webhook_clears_sender_when_disabled(self):
        """_rebuild_webhook with webhook_enabled=False sets _webhook to None."""
        config_initial = {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_auth_type": "none",
        }
        node = _make_node(config=config_initial)
        assert node._webhook is not None

        node._rebuild_webhook({"webhook_enabled": False})
        assert node._webhook is None

    def test_rebuild_webhook_updates_config(self):
        """_rebuild_webhook updates self._config."""
        node = _make_node()
        new_config = {"webhook_enabled": False, "some_other": "value"}
        node._rebuild_webhook(new_config)
        assert node._config == new_config
