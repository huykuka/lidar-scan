"""Integration tests for the shapes WebSocket topic (BE-05, BE-07, BE-08)."""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestShapesSystemTopic:
    def test_shapes_in_system_topics(self):
        from app.services.websocket.manager import SYSTEM_TOPICS
        assert "shapes" in SYSTEM_TOPICS

    def test_shapes_not_in_public_topics(self):
        from app.services.websocket.manager import ConnectionManager
        mgr = ConnectionManager()
        mgr.register_topic("shapes")
        mgr.register_topic("some_node_abc123")
        public = mgr.get_public_topics()
        assert "shapes" not in public
        assert "some_node_abc123" in public

    def test_shapes_topic_registered_at_startup(self):
        """shapes topic is pre-registered and survives after being registered."""
        from app.services.websocket.manager import ConnectionManager
        mgr = ConnectionManager()
        mgr.register_topic("shapes")
        assert "shapes" in mgr._registered_topics

    def test_shapes_topic_has_subscribers_check(self):
        from app.services.websocket.manager import ConnectionManager
        mgr = ConnectionManager()
        mgr.register_topic("shapes")
        assert not mgr.has_subscribers("shapes")


class TestShapeAggregation:
    @pytest.mark.asyncio
    async def test_shape_frame_broadcast(self):
        """DataRouter collects shapes from ShapeCollectorMixin nodes and broadcasts."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        from app.services.nodes.shapes import CubeShape

        # Create a mock node that implements ShapeCollectorMixin
        class MockNode(ShapeCollectorMixin):
            def __init__(self):
                super().__init__()
                self.id = "node-test-001"
                self.name = "Test Node"

        node = MockNode()
        node.emit_shape(CubeShape(center=[1, 2, 3], size=[1, 1, 1]))

        # Verify shapes are collected
        shapes = node.collect_and_clear_shapes()
        assert len(shapes) == 1
        assert shapes[0].type == "cube"

    @pytest.mark.asyncio
    async def test_shapes_broadcast_via_routing(self):
        """DataRouter.publish_shapes broadcasts a ShapeFrame to 'shapes' topic."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        from app.services.nodes.shapes import CubeShape, compute_shape_id
        from app.services.nodes.managers.routing import DataRouter

        class MockNode(ShapeCollectorMixin):
            def __init__(self):
                super().__init__()
                self.id = "node-test-001"
                self.name = "Test Node"

        node = MockNode()
        node.emit_shape(CubeShape(center=[1, 2, 3], size=[1, 1, 1]))

        mock_manager = MagicMock()
        mock_manager.nodes = {"node-test-001": node}

        router = DataRouter(mock_manager)

        broadcast_calls = []

        async def mock_broadcast(topic, payload):
            broadcast_calls.append((topic, payload))

        with patch("app.services.nodes.managers.routing.manager") as mock_ws_mgr:
            mock_ws_mgr.has_subscribers.return_value = True
            mock_ws_mgr.broadcast = AsyncMock(side_effect=mock_broadcast)
            await router.publish_shapes()

        assert len(broadcast_calls) == 1
        topic, payload = broadcast_calls[0]
        assert topic == "shapes"
        assert "shapes" in payload
        assert len(payload["shapes"]) == 1
        shape_data = payload["shapes"][0]
        assert shape_data["node_name"] == "Test Node"
        assert shape_data["id"].startswith("shape_")

    @pytest.mark.asyncio
    async def test_empty_shapes_still_broadcasts_with_subscribers(self):
        """Even with no shapes, we broadcast empty frame when subscribers exist."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services.nodes.managers.routing import DataRouter

        mock_manager = MagicMock()
        mock_manager.nodes = {}

        router = DataRouter(mock_manager)
        broadcast_calls = []

        async def mock_broadcast(topic, payload):
            broadcast_calls.append((topic, payload))

        with patch("app.services.nodes.managers.routing.manager") as mock_ws_mgr:
            mock_ws_mgr.has_subscribers.return_value = True
            mock_ws_mgr.broadcast = AsyncMock(side_effect=mock_broadcast)
            await router.publish_shapes()

        assert len(broadcast_calls) == 1
        assert broadcast_calls[0][1]["shapes"] == []

    @pytest.mark.asyncio
    async def test_no_broadcast_when_no_shapes_and_no_subscribers(self):
        """No broadcast when empty shapes and no subscribers."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services.nodes.managers.routing import DataRouter

        mock_manager = MagicMock()
        mock_manager.nodes = {}

        router = DataRouter(mock_manager)
        broadcast_calls = []

        with patch("app.services.nodes.managers.routing.manager") as mock_ws_mgr:
            mock_ws_mgr.has_subscribers.return_value = False
            mock_ws_mgr.broadcast = AsyncMock(side_effect=lambda t, p: broadcast_calls.append((t, p)))
            await router.publish_shapes()

        assert len(broadcast_calls) == 0


class TestShapeCountCap:
    @pytest.mark.asyncio
    async def test_shapes_capped_at_500(self):
        """Shape count is capped at 500 in aggregation."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        from app.services.nodes.shapes import LabelShape
        from app.services.nodes.managers.routing import DataRouter

        class MockNode(ShapeCollectorMixin):
            def __init__(self):
                super().__init__()
                self.id = "node-big"
                self.name = "Big Node"

        node = MockNode()
        for i in range(600):
            node.emit_shape(LabelShape(position=[float(i), 0, 0], text=f"label_{i}"))

        mock_manager = MagicMock()
        mock_manager.nodes = {"node-big": node}
        router = DataRouter(mock_manager)

        broadcast_calls = []

        with patch("app.services.nodes.managers.routing.manager") as mock_ws_mgr:
            mock_ws_mgr.has_subscribers.return_value = True
            mock_ws_mgr.broadcast = AsyncMock(side_effect=lambda t, p: broadcast_calls.append((t, p)))
            await router.publish_shapes()

        payload = broadcast_calls[0][1]
        assert len(payload["shapes"]) == 500


class TestHandleIncomingDataPublishesShapes:
    """Verify publish_shapes() is called after every handle_incoming_data cycle."""

    @pytest.mark.asyncio
    async def test_publish_shapes_called_after_on_input(self):
        """
        handle_incoming_data must call publish_shapes() after on_input() returns,
        so shapes emitted by ShapeCollectorMixin nodes are broadcast on the same frame.
        """
        from app.services.nodes.managers.routing import DataRouter
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        from app.services.nodes.shapes import CubeShape

        shapes_broadcast: list = []

        class FakeShapeNode(ShapeCollectorMixin):
            def __init__(self):
                super().__init__()
                self.id = "node-shape-001"
                self.name = "FakeShapeNode"

            async def on_input(self, payload):
                self.emit_shape(CubeShape(center=[0, 0, 0], size=[1, 1, 1]))

        node = FakeShapeNode()
        mock_manager = MagicMock()
        mock_manager.nodes = {"node-shape-001": node}

        router = DataRouter(mock_manager)

        with patch("app.services.nodes.managers.routing.manager") as mock_ws_mgr:
            mock_ws_mgr.has_subscribers.return_value = True
            mock_ws_mgr.broadcast = AsyncMock(
                side_effect=lambda t, p: shapes_broadcast.append((t, p))
            )
            await router.handle_incoming_data({"node_id": "node-shape-001"})

        # publish_shapes() must have been called and broadcast one shape
        assert len(shapes_broadcast) == 1
        topic, payload = shapes_broadcast[0]
        assert topic == "shapes"
        assert len(payload["shapes"]) == 1
        assert payload["shapes"][0]["node_name"] == "FakeShapeNode"

    @pytest.mark.asyncio
    async def test_publish_shapes_called_even_when_no_shapes_emitted(self):
        """
        publish_shapes() is still called (and broadcasts empty frame to subscribers)
        even when no shape-emitting node exists in this frame.
        """
        from app.services.nodes.managers.routing import DataRouter

        class PlainNode:
            id = "node-plain-001"
            name = "PlainNode"

            async def on_input(self, payload):
                pass  # no shapes emitted

        node = PlainNode()
        mock_manager = MagicMock()
        mock_manager.nodes = {"node-plain-001": node}

        router = DataRouter(mock_manager)
        broadcast_calls: list = []

        with patch("app.services.nodes.managers.routing.manager") as mock_ws_mgr:
            # has_subscribers=True → empty ShapeFrame is still broadcast
            mock_ws_mgr.has_subscribers.return_value = True
            mock_ws_mgr.broadcast = AsyncMock(
                side_effect=lambda t, p: broadcast_calls.append((t, p))
            )
            await router.handle_incoming_data({"node_id": "node-plain-001"})

        assert len(broadcast_calls) == 1
        assert broadcast_calls[0][0] == "shapes"
        assert broadcast_calls[0][1]["shapes"] == []

    @pytest.mark.asyncio
    async def test_no_broadcast_when_no_shapes_and_no_subscribers(self):
        """
        When no shapes are emitted and no WS subscriber is listening, nothing is broadcast.
        """
        from app.services.nodes.managers.routing import DataRouter

        class PlainNode:
            id = "node-plain-002"
            name = "PlainNode2"

            async def on_input(self, payload):
                pass

        node = PlainNode()
        mock_manager = MagicMock()
        mock_manager.nodes = {"node-plain-002": node}

        router = DataRouter(mock_manager)
        broadcast_calls: list = []

        with patch("app.services.nodes.managers.routing.manager") as mock_ws_mgr:
            mock_ws_mgr.has_subscribers.return_value = False
            mock_ws_mgr.broadcast = AsyncMock(
                side_effect=lambda t, p: broadcast_calls.append((t, p))
            )
            await router.handle_incoming_data({"node_id": "node-plain-002"})

        assert len(broadcast_calls) == 0
