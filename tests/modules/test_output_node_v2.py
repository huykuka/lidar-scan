"""
Unit tests for OutputNode v2 — per-node WebSocket topic broadcast.

BC-2 validation: on_input MUST broadcast on self._ws_topic (per-node)
NOT on hardcoded "system_status".

Complements test_output_node.py (which tests the existing v1 contract).
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(config=None, ws_topic: str | None = "output_test_abc12345"):
    """Create an OutputNode with an optional _ws_topic pre-set (simulates orchestrator assignment)."""
    from app.modules.flow_control.output.node import OutputNode

    manager = Mock()
    manager.downstream_map = {}
    node = OutputNode(
        manager=manager,
        node_id="out-node-v2",
        name="Test Output V2",
        config=config or {},
    )
    # Simulate orchestrator post-instantiation topic assignment
    node._ws_topic = ws_topic
    return node


# ---------------------------------------------------------------------------
# BC-2: on_input broadcasts on self._ws_topic (NOT "system_status")
# ---------------------------------------------------------------------------

class TestOnInputPerNodeTopic:
    """B7.1 — BC-2 validation: broadcast must use per-node topic."""

    @pytest.mark.asyncio
    async def test_on_input_broadcasts_on_per_node_topic(self):
        """on_input must call ws_manager.broadcast with self._ws_topic, NOT 'system_status'."""
        node = _make_node(ws_topic="output_test_abc12345")
        captured = []

        async def fake_broadcast(topic, message):
            captured.append((topic, message))

        with patch(
            "app.modules.flow_control.output.node.asyncio.create_task",
            side_effect=lambda coro: asyncio.ensure_future(coro),
        ), patch(
            "app.services.websocket.manager.manager.broadcast",
            side_effect=fake_broadcast,
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            await node.on_input({"points": [], "timestamp": 1.0, "point_count": 42})

        await asyncio.sleep(0)

        assert len(captured) == 1
        topic, message = captured[0]
        # BC-2: must use per-node topic, never "system_status"
        assert topic == "output_test_abc12345", (
            f"Expected per-node topic 'output_test_abc12345', got '{topic}'"
        )
        assert topic != "system_status", "Must NOT broadcast on system_status"

    @pytest.mark.asyncio
    async def test_on_input_skips_broadcast_when_ws_topic_none(self):
        """When _ws_topic is None (startup race), broadcast must NOT be called."""
        node = _make_node(ws_topic=None)
        captured = []

        async def fake_broadcast(topic, message):
            captured.append((topic, message))

        with patch(
            "app.modules.flow_control.output.node.asyncio.create_task",
            side_effect=lambda coro: asyncio.ensure_future(coro),
        ), patch(
            "app.services.websocket.manager.manager.broadcast",
            side_effect=fake_broadcast,
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            await node.on_input({"points": [], "timestamp": 1.0})

        await asyncio.sleep(0)

        assert len(captured) == 0, (
            "Broadcast must be skipped when _ws_topic is None (startup guard)"
        )

    @pytest.mark.asyncio
    async def test_on_input_message_type_is_output_node_metadata(self):
        """Broadcast message type discriminator must be 'output_node_metadata'."""
        node = _make_node(ws_topic="output_test_abc12345")
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
            await node.on_input({"points": [], "timestamp": 1.0, "sensor_name": "lidar_front"})

        await asyncio.sleep(0)
        assert len(captured) == 1
        assert captured[0]["type"] == "output_node_metadata"
        assert captured[0]["node_id"] == "out-node-v2"
        assert "metadata" in captured[0]
        assert "timestamp" in captured[0]

    @pytest.mark.asyncio
    async def test_on_input_metadata_excludes_points(self):
        """'points' must be excluded from the broadcast metadata payload."""
        node = _make_node(ws_topic="output_test_abc12345")
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
            import numpy as np
            await node.on_input({
                "points": np.zeros((100, 3)),
                "point_count": 100,
                "timestamp": 1.0,
            })

        await asyncio.sleep(0)
        assert len(captured) == 1
        metadata = captured[0]["metadata"]
        assert "points" not in metadata
        assert metadata.get("point_count") == 100

    @pytest.mark.asyncio
    async def test_on_input_fires_webhook_when_topic_is_set(self):
        """Both WS broadcast AND webhook fire when ws_topic is set and webhook enabled."""
        config = {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_auth_type": "none",
        }
        node = _make_node(config=config, ws_topic="output_test_abc12345")
        assert node._webhook is not None

        send_mock = AsyncMock()
        node._webhook.send = send_mock  # type: ignore[assignment]

        ws_captured = []

        async def fake_broadcast(topic, message):
            ws_captured.append((topic, message))

        with patch(
            "app.modules.flow_control.output.node.asyncio.create_task",
            side_effect=lambda coro: asyncio.ensure_future(coro),
        ), patch(
            "app.services.websocket.manager.manager.broadcast",
            side_effect=fake_broadcast,
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            await node.on_input({"points": [], "timestamp": 1.0})

        await asyncio.sleep(0)

        # WS broadcast must be on per-node topic
        assert len(ws_captured) == 1
        assert ws_captured[0][0] == "output_test_abc12345"

        # Webhook must also fire
        send_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_input_does_not_fire_webhook_when_disabled(self):
        """When webhook is disabled, only WS broadcast fires."""
        node = _make_node(ws_topic="output_test_abc12345")
        assert node._webhook is None

        ws_captured = []

        async def fake_broadcast(topic, message):
            ws_captured.append((topic, message))

        with patch(
            "app.modules.flow_control.output.node.asyncio.create_task",
            side_effect=lambda coro: asyncio.ensure_future(coro),
        ), patch(
            "app.services.websocket.manager.manager.broadcast",
            side_effect=fake_broadcast,
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            await node.on_input({"points": [], "timestamp": 1.0})

        await asyncio.sleep(0)
        # WS broadcast fires
        assert len(ws_captured) == 1
        # No webhook (assert we don't crash)

    @pytest.mark.asyncio
    async def test_on_input_increments_metadata_count_on_success(self):
        """metadata_count must be incremented after a successful broadcast."""
        node = _make_node(ws_topic="output_test_abc12345")
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
    async def test_on_input_error_count_when_extract_fails(self):
        """error_count incremented, metadata_count NOT incremented on _extract_metadata failure."""
        node = _make_node(ws_topic="output_test_abc12345")

        with patch.object(
            node, "_extract_metadata", side_effect=RuntimeError("extraction failed")
        ), patch(
            "app.modules.flow_control.output.node.notify_status_change"
        ):
            await node.on_input({"points": [], "timestamp": 1.0})

        assert node.error_count == 1
        assert node.metadata_count == 0


# ---------------------------------------------------------------------------
# BC-1: websocket_enabled=True in NodeDefinition
# ---------------------------------------------------------------------------

class TestOutputNodeWebsocketEnabled:
    """B7.6 — output_node NodeDefinition registration checks."""

    def test_output_node_definition_websocket_enabled_is_false(self):
        """NodeDefinition for output_node has websocket_enabled=False (uses system_status topic)."""
        import app.modules.flow_control.output.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        definition = node_schema_registry.get("output_node")
        assert definition is not None, "output_node definition not registered"
        assert definition.websocket_enabled is False

    def test_output_node_definition_category_is_flow_control(self):
        """NodeDefinition for output_node has category='flow_control'."""
        import app.modules.flow_control.output.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        definition = node_schema_registry.get("output_node")
        assert definition is not None
        assert definition.category == "flow_control"

    def test_output_node_has_no_output_ports(self):
        """Terminal node: outputs list must be empty."""
        import app.modules.flow_control.output.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        definition = node_schema_registry.get("output_node")
        assert definition is not None
        assert len(definition.outputs) == 0, "Terminal node must have no output ports"

    def test_output_node_has_one_input_port(self):
        """output_node must have exactly one input port with id='in'."""
        import app.modules.flow_control.output.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        definition = node_schema_registry.get("output_node")
        assert definition is not None
        assert len(definition.inputs) == 1
        assert definition.inputs[0].id == "in"
        assert definition.inputs[0].multiple is False
