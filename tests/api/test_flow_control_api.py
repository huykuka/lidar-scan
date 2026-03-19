"""
Tests for Flow Control API endpoints.

Tests the REST API for external state control of IF condition nodes.
Both endpoints require no request body — the action is encoded in the URL.
"""
import pytest
from unittest.mock import Mock, patch
from app.modules.flow_control.if_condition.node import IfConditionNode


class TestSetExternalStateEndpoint:
    """Test POST /nodes/{node_id}/flow-control/set endpoint"""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_returns_200(self, mock_manager, client):
        """Calling /set returns HTTP 200"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/test-node/flow-control/set")

        assert response.status_code == 200

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_always_sets_state_to_true(self, mock_manager, client):
        """/set always sets external_state to True regardless of prior state"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node

        client.post("/api/v1/nodes/test-node/flow-control/set")

        assert mock_node.external_state is True

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_accepts_no_body(self, mock_manager, client):
        """/set succeeds with an empty body"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/test-node/flow-control/set")

        assert response.status_code == 200

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_response_contains_node_id(self, mock_manager, client):
        """Response includes the correct node_id"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/my-node-id/flow-control/set")

        data = response.json()
        assert "node_id" in data
        assert data["node_id"] == "my-node-id"

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_response_state_is_true(self, mock_manager, client):
        """Response state field is always True after /set"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/test-node/flow-control/set")

        data = response.json()
        assert "state" in data
        assert data["state"] is True

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_response_contains_timestamp(self, mock_manager, client):
        """Response includes a positive timestamp"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/test-node/flow-control/set")

        data = response.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], (int, float))
        assert data["timestamp"] > 0

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_node_not_found_returns_404(self, mock_manager, client):
        """Non-existent node returns HTTP 404"""
        mock_manager.nodes.get.return_value = None

        response = client.post("/api/v1/nodes/non-existent-node/flow-control/set")

        assert response.status_code == 404
        assert "detail" in response.json()

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_wrong_node_type_returns_404(self, mock_manager, client):
        """Node of wrong type (not IfConditionNode) returns HTTP 404"""
        mock_node = Mock()  # generic Mock, not spec=IfConditionNode
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/wrong-type-node/flow-control/set")

        assert response.status_code == 404
        assert "not a flow control node" in response.json()["detail"].lower()


class TestResetExternalStateEndpoint:
    """Test POST /nodes/{node_id}/flow-control/reset endpoint"""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_returns_200(self, mock_manager, client):
        """Calling /reset returns HTTP 200"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = True
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/test-node/flow-control/reset")

        assert response.status_code == 200

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_always_sets_state_to_false(self, mock_manager, client):
        """/reset always sets external_state to False"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = True
        mock_manager.nodes.get.return_value = mock_node

        client.post("/api/v1/nodes/test-node/flow-control/reset")

        assert mock_node.external_state is False

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_response_contains_node_id(self, mock_manager, client):
        """Response includes the correct node_id"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = True
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/my-reset-node/flow-control/reset")

        data = response.json()
        assert "node_id" in data
        assert data["node_id"] == "my-reset-node"

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_response_state_is_false(self, mock_manager, client):
        """Response state field is always False after /reset"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = True
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/test-node/flow-control/reset")

        data = response.json()
        assert "state" in data
        assert data["state"] is False

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_response_contains_timestamp(self, mock_manager, client):
        """Response includes a positive timestamp"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = True
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/test-node/flow-control/reset")

        data = response.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], (int, float))

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_node_not_found_returns_404(self, mock_manager, client):
        """Non-existent node returns HTTP 404"""
        mock_manager.nodes.get.return_value = None

        response = client.post("/api/v1/nodes/non-existent/flow-control/reset")

        assert response.status_code == 404

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_wrong_node_type_returns_404(self, mock_manager, client):
        """Node of wrong type returns HTTP 404"""
        mock_node = Mock()
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/wrong-type/flow-control/reset")

        assert response.status_code == 404
        assert "not a flow control node" in response.json()["detail"].lower()

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_already_false_still_returns_200(self, mock_manager, client):
        """Resetting already-false state still succeeds"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node

        response = client.post("/api/v1/nodes/test-node/flow-control/reset")

        assert response.status_code == 200
        assert response.json()["state"] is False


class TestFlowControlEndpointsIntegration:
    """Integration tests combining set and reset operations"""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_then_reset_workflow(self, mock_manager, client):
        """Calling /set then /reset correctly toggles state"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node

        response1 = client.post("/api/v1/nodes/test-node/flow-control/set")
        assert response1.status_code == 200
        assert mock_node.external_state is True

        response2 = client.post("/api/v1/nodes/test-node/flow-control/reset")
        assert response2.status_code == 200
        assert mock_node.external_state is False

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_multiple_sets_keep_state_true(self, mock_manager, client):
        """Calling /set multiple times is idempotent"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node

        client.post("/api/v1/nodes/test-node/flow-control/set")
        client.post("/api/v1/nodes/test-node/flow-control/set")
        client.post("/api/v1/nodes/test-node/flow-control/set")

        assert mock_node.external_state is True

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_timestamps_increase_monotonically(self, mock_manager, client):
        """Each request returns a non-decreasing timestamp"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node

        ts1 = client.post("/api/v1/nodes/test-node/flow-control/set").json()["timestamp"]
        ts2 = client.post("/api/v1/nodes/test-node/flow-control/reset").json()["timestamp"]
        ts3 = client.post("/api/v1/nodes/test-node/flow-control/set").json()["timestamp"]

        assert ts2 >= ts1
        assert ts3 >= ts2
