"""
Tests for Flow Control API endpoints.

Tests the REST API for external state control of IF condition nodes.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.modules.flow_control.if_condition.node import IfConditionNode


class TestSetExternalStateEndpoint:
    """Test POST /nodes/{node_id}/flow-control/set endpoint"""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_state_to_true_returns_200(self, mock_manager, client):
        """Setting external state to True returns HTTP 200"""
        # Create mock IF node
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post(
            "/api/v1/nodes/test-if-node/flow-control/set",
            json={"value": True}
        )
        
        assert response.status_code == 200
        assert mock_node.external_state is True

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_state_to_false_returns_200(self, mock_manager, client):
        """Setting external state to False returns HTTP 200"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = True
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post(
            "/api/v1/nodes/test-if-node/flow-control/set",
            json={"value": False}
        )
        
        assert response.status_code == 200
        assert mock_node.external_state is False

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_response_contains_node_id(self, mock_manager, client):
        """Response includes node_id field"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post(
            "/api/v1/nodes/my-node-id/flow-control/set",
            json={"value": True}
        )
        
        data = response.json()
        assert "node_id" in data
        assert data["node_id"] == "my-node-id"

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_response_contains_state(self, mock_manager, client):
        """Response includes state field matching request"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post(
            "/api/v1/nodes/test-node/flow-control/set",
            json={"value": True}
        )
        
        data = response.json()
        assert "state" in data
        assert data["state"] is True

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_response_contains_timestamp(self, mock_manager, client):
        """Response includes timestamp field"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post(
            "/api/v1/nodes/test-node/flow-control/set",
            json={"value": True}
        )
        
        data = response.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], (int, float))
        assert data["timestamp"] > 0

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_invalid_value_type_returns_422(self, mock_manager, client):
        """Sending non-boolean value returns HTTP 422 (Pydantic validation)"""
        mock_node = Mock(spec=IfConditionNode)
        mock_manager.nodes.get.return_value = mock_node
        
        # String instead of boolean
        response = client.post(
            "/api/v1/nodes/test-node/flow-control/set",
            json={"value": "true"}
        )
        
        assert response.status_code == 422

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_invalid_value_type_number_returns_422(self, mock_manager, client):
        """Sending number value returns HTTP 422"""
        mock_node = Mock(spec=IfConditionNode)
        mock_manager.nodes.get.return_value = mock_node
        
        # Number instead of boolean
        response = client.post(
            "/api/v1/nodes/test-node/flow-control/set",
            json={"value": 1}
        )
        
        assert response.status_code == 422

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_missing_value_field_returns_422(self, mock_manager, client):
        """Missing 'value' field returns HTTP 422"""
        mock_node = Mock(spec=IfConditionNode)
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post(
            "/api/v1/nodes/test-node/flow-control/set",
            json={}
        )
        
        assert response.status_code == 422

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_node_not_found_returns_404(self, mock_manager, client):
        """Non-existent node returns HTTP 404"""
        mock_manager.nodes.get.return_value = None
        
        response = client.post(
            "/api/v1/nodes/non-existent-node/flow-control/set",
            json={"value": True}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_wrong_node_type_returns_404(self, mock_manager, client):
        """Node of wrong type (not IfConditionNode) returns HTTP 404"""
        # Create a mock node that is NOT an IfConditionNode
        mock_node = Mock()  # Just a generic Mock, not spec=IfConditionNode
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post(
            "/api/v1/nodes/wrong-type-node/flow-control/set",
            json={"value": True}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not a flow control node" in data["detail"].lower()


class TestResetExternalStateEndpoint:
    """Test POST /nodes/{node_id}/flow-control/reset endpoint"""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_state_returns_200(self, mock_manager, client):
        """Resetting state returns HTTP 200"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = True
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post("/api/v1/nodes/test-node/flow-control/reset")
        
        assert response.status_code == 200

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_sets_state_to_false(self, mock_manager, client):
        """Reset endpoint sets external_state to False"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = True
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post("/api/v1/nodes/test-node/flow-control/reset")
        
        assert mock_node.external_state is False

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_response_contains_node_id(self, mock_manager, client):
        """Response includes node_id field"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = True
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post("/api/v1/nodes/my-reset-node/flow-control/reset")
        
        data = response.json()
        assert "node_id" in data
        assert data["node_id"] == "my-reset-node"

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_response_state_is_false(self, mock_manager, client):
        """Response state field is always False after reset"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = True
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post("/api/v1/nodes/test-node/flow-control/reset")
        
        data = response.json()
        assert "state" in data
        assert data["state"] is False

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_response_contains_timestamp(self, mock_manager, client):
        """Response includes timestamp field"""
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
        mock_node = Mock()  # Not an IfConditionNode
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post("/api/v1/nodes/wrong-type/flow-control/reset")
        
        assert response.status_code == 404
        data = response.json()
        assert "not a flow control node" in data["detail"].lower()

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_reset_already_false_still_returns_200(self, mock_manager, client):
        """Resetting already-false state still succeeds"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node
        
        response = client.post("/api/v1/nodes/test-node/flow-control/reset")
        
        assert response.status_code == 200
        data = response.json()
        assert data["state"] is False


class TestFlowControlEndpointsIntegration:
    """Integration tests combining set and reset operations"""

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_set_then_reset_workflow(self, mock_manager, client):
        """Setting state to True then resetting works correctly"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node
        
        # Set to True
        response1 = client.post(
            "/api/v1/nodes/test-node/flow-control/set",
            json={"value": True}
        )
        assert response1.status_code == 200
        assert mock_node.external_state is True
        
        # Reset to False
        response2 = client.post("/api/v1/nodes/test-node/flow-control/reset")
        assert response2.status_code == 200
        assert mock_node.external_state is False

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_multiple_sets_update_state(self, mock_manager, client):
        """Multiple set operations correctly update state"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node
        
        # Set to True
        client.post(
            "/api/v1/nodes/test-node/flow-control/set",
            json={"value": True}
        )
        assert mock_node.external_state is True
        
        # Set to False
        client.post(
            "/api/v1/nodes/test-node/flow-control/set",
            json={"value": False}
        )
        assert mock_node.external_state is False
        
        # Set to True again
        client.post(
            "/api/v1/nodes/test-node/flow-control/set",
            json={"value": True}
        )
        assert mock_node.external_state is True

    @patch("app.api.v1.flow_control.service.node_manager")
    def test_timestamps_increase_monotonically(self, mock_manager, client):
        """Each request returns increasing timestamps"""
        mock_node = Mock(spec=IfConditionNode)
        mock_node.external_state = False
        mock_manager.nodes.get.return_value = mock_node
        
        response1 = client.post(
            "/api/v1/nodes/test-node/flow-control/set",
            json={"value": True}
        )
        ts1 = response1.json()["timestamp"]
        
        response2 = client.post("/api/v1/nodes/test-node/flow-control/reset")
        ts2 = response2.json()["timestamp"]
        
        response3 = client.post(
            "/api/v1/nodes/test-node/flow-control/set",
            json={"value": True}
        )
        ts3 = response3.json()["timestamp"]
        
        assert ts2 >= ts1
        assert ts3 >= ts2
