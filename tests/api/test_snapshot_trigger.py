"""
Integration tests for POST /api/v1/nodes/{node_id}/trigger endpoint.

TDD phase — written before implementation. Tests the full HTTP contract
defined in api-spec.md §1.
"""
import time
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch

from app.modules.flow_control.snapshot.node import SnapshotNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot_node(throttle_ms: float = 0, node_id: str = "snap-1") -> SnapshotNode:
    manager = Mock()
    manager.forward_data = AsyncMock()
    return SnapshotNode(
        manager=manager,
        node_id=node_id,
        name="Test Snapshot",
        throttle_ms=throttle_ms,
    )


# ---------------------------------------------------------------------------
# TestSnapshotTriggerEndpointSuccess
# ---------------------------------------------------------------------------

class TestSnapshotTriggerEndpointSuccess:
    """200 OK responses."""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_returns_200_after_seeding_payload(self, mock_manager, client):
        """Happy path: node exists, has payload → 200 {"status": "ok"}."""
        node = _make_snapshot_node()
        # Seed payload synchronously
        asyncio.get_event_loop().run_until_complete(
            node.on_input({"points": [1, 2], "timestamp": 1.0})
        )
        mock_manager.nodes.get.return_value = node

        response = client.post("/api/v1/nodes/snap-1/trigger")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_response_matches_schema(self, mock_manager, client):
        """Response body contains exactly {status: 'ok'}."""
        node = _make_snapshot_node()
        asyncio.get_event_loop().run_until_complete(
            node.on_input({"points": [], "timestamp": 0.0})
        )
        mock_manager.nodes.get.return_value = node

        data = client.post("/api/v1/nodes/snap-1/trigger").json()

        assert set(data.keys()) == {"status"}
        assert data["status"] == "ok"

    @patch("app.api.v1.flow_control.service.node_manager")
    @patch("app.modules.flow_control.snapshot.node.notify_status_change")
    def test_notify_status_change_called_on_success(self, mock_notify, mock_manager, client):
        """notify_status_change is invoked after a successful trigger."""
        node = _make_snapshot_node()
        asyncio.get_event_loop().run_until_complete(
            node.on_input({"points": [], "timestamp": 0.0})
        )
        mock_manager.nodes.get.return_value = node

        client.post("/api/v1/nodes/snap-1/trigger")

        mock_notify.assert_called_once_with("snap-1")


# ---------------------------------------------------------------------------
# TestSnapshotTriggerEndpoint404
# ---------------------------------------------------------------------------

class TestSnapshotTriggerEndpoint404:
    """404 Not Found responses."""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_returns_404_when_node_not_in_manager(self, mock_manager, client):
        """Node absent from node_manager → 404."""
        mock_manager.nodes.get.return_value = None

        response = client.post("/api/v1/nodes/nonexistent/trigger")

        assert response.status_code == 404
        assert "detail" in response.json()

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_returns_404_when_no_upstream_data(self, mock_manager, client):
        """Node exists but _latest_payload is None → 404."""
        node = _make_snapshot_node()
        assert node._latest_payload is None
        mock_manager.nodes.get.return_value = node

        response = client.post("/api/v1/nodes/snap-1/trigger")

        assert response.status_code == 404
        assert "detail" in response.json()


# ---------------------------------------------------------------------------
# TestSnapshotTriggerEndpoint400
# ---------------------------------------------------------------------------

class TestSnapshotTriggerEndpoint400:
    """400 Bad Request — wrong node type."""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_returns_400_for_non_snapshot_node(self, mock_manager, client):
        """node_id resolves to a non-SnapshotNode → 400."""
        from app.modules.flow_control.if_condition.node import IfConditionNode
        wrong_node = Mock(spec=IfConditionNode)
        mock_manager.nodes.get.return_value = wrong_node

        response = client.post("/api/v1/nodes/wrong-type/trigger")

        assert response.status_code == 400
        assert "detail" in response.json()


# ---------------------------------------------------------------------------
# TestSnapshotTriggerEndpoint409
# ---------------------------------------------------------------------------

class TestSnapshotTriggerEndpoint409:
    """409 Conflict — concurrent trigger guard."""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_returns_409_when_processing(self, mock_manager, client):
        """_is_processing=True at request time → 409."""
        node = _make_snapshot_node()
        asyncio.get_event_loop().run_until_complete(
            node.on_input({"points": [], "timestamp": 0.0})
        )
        node._is_processing = True
        mock_manager.nodes.get.return_value = node

        response = client.post("/api/v1/nodes/snap-1/trigger")

        assert response.status_code == 409
        assert "detail" in response.json()


# ---------------------------------------------------------------------------
# TestSnapshotTriggerEndpoint429
# ---------------------------------------------------------------------------

class TestSnapshotTriggerEndpoint429:
    """429 Too Many Requests — throttle window guard."""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_returns_429_within_throttle_window(self, mock_manager, client):
        """Second call within throttle_ms window → 429."""
        node = _make_snapshot_node(throttle_ms=500)
        asyncio.get_event_loop().run_until_complete(
            node.on_input({"points": [], "timestamp": 0.0})
        )
        # Simulate recent trigger
        node._last_trigger_time = time.time() - 0.1  # 100ms ago, within 500ms window
        mock_manager.nodes.get.return_value = node

        response = client.post("/api/v1/nodes/snap-1/trigger")

        assert response.status_code == 429
        assert "detail" in response.json()


# ---------------------------------------------------------------------------
# TestSnapshotTriggerEndpoint500
# ---------------------------------------------------------------------------

class TestSnapshotTriggerEndpoint500:
    """500 Internal Server Error — forward_data failure."""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_returns_500_when_forward_data_raises(self, mock_manager, client):
        """manager.forward_data raises → 500."""
        node = _make_snapshot_node()
        node.manager.forward_data = AsyncMock(side_effect=RuntimeError("downstream crash"))
        asyncio.get_event_loop().run_until_complete(
            node.on_input({"points": [], "timestamp": 0.0})
        )
        mock_manager.nodes.get.return_value = node

        response = client.post("/api/v1/nodes/snap-1/trigger")

        assert response.status_code == 500
        assert "detail" in response.json()

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_emit_status_error_after_forward_failure(self, mock_manager, client):
        """After a 500, emit_status() reports ERROR."""
        node = _make_snapshot_node()
        node.manager.forward_data = AsyncMock(side_effect=RuntimeError("boom"))
        asyncio.get_event_loop().run_until_complete(
            node.on_input({"points": [], "timestamp": 0.0})
        )
        mock_manager.nodes.get.return_value = node

        client.post("/api/v1/nodes/snap-1/trigger")

        status = node.emit_status()
        from app.schemas.status import OperationalState
        assert status.operational_state == OperationalState.ERROR


# ---------------------------------------------------------------------------
# TestSnapshotConcurrency
# ---------------------------------------------------------------------------

class TestSnapshotConcurrency:
    """Concurrency and rapid-fire tests per qa-tasks.md."""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_two_concurrent_triggers_one_200_one_409(self, mock_manager, client):
        """Two simultaneous POST calls: exactly one 200, one 409."""
        # We simulate by manually toggling _is_processing
        node = _make_snapshot_node()
        asyncio.get_event_loop().run_until_complete(
            node.on_input({"points": [], "timestamp": 0.0})
        )
        mock_manager.nodes.get.return_value = node

        # First trigger (should succeed)
        r1 = client.post("/api/v1/nodes/snap-1/trigger")
        # Simulate second concurrent trigger (node is now processing)
        node._is_processing = True
        r2 = client.post("/api/v1/nodes/snap-1/trigger")
        node._is_processing = False

        statuses = sorted([r1.status_code, r2.status_code])
        assert statuses == [200, 409]

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_rapid_triggers_with_throttle_only_first_200(self, mock_manager, client):
        """With throttle_ms=500: first call 200, subsequent calls 429."""
        node = _make_snapshot_node(throttle_ms=500)
        asyncio.get_event_loop().run_until_complete(
            node.on_input({"points": [], "timestamp": 0.0})
        )
        mock_manager.nodes.get.return_value = node

        results = []
        for _ in range(5):
            r = client.post("/api/v1/nodes/snap-1/trigger")
            results.append(r.status_code)

        # First should be 200, rest 429
        assert results[0] == 200
        assert all(s == 429 for s in results[1:])


# ---------------------------------------------------------------------------
# TestSnapshotRegistryDAG
# ---------------------------------------------------------------------------

class TestSnapshotRegistryDAG:
    """Registry and DAG integration per qa-tasks.md."""

    def test_snapshot_in_node_schema_registry(self):
        """'snapshot' type must be present in the schema registry."""
        from app.services.nodes.schema import node_schema_registry
        # Ensure snapshot registry is loaded
        import app.modules.flow_control.snapshot.registry  # noqa: F401
        definitions = {d.type: d for d in node_schema_registry.get_all()}
        assert "snapshot" in definitions

    def test_node_factory_builds_snapshot_node(self):
        """NodeFactory.create({'type': 'snapshot', ...}) must return a SnapshotNode."""
        from app.services.nodes.node_factory import NodeFactory
        import app.modules.flow_control.snapshot.registry  # noqa: F401

        manager = Mock()
        manager.forward_data = AsyncMock()
        node_cfg = {
            "id": "snap-factory-test",
            "name": "Factory Snapshot",
            "type": "snapshot",
            "config": {"throttle_ms": 100},
        }
        result = NodeFactory.create(node_cfg, manager, [])
        assert isinstance(result, SnapshotNode)
        assert result.id == "snap-factory-test"
        assert result.throttle_ms == 100

    def test_snapshot_node_ws_topic_none(self):
        """SnapshotNode._ws_topic is None — no WebSocket topic registered."""
        node = _make_snapshot_node()
        assert node._ws_topic is None
