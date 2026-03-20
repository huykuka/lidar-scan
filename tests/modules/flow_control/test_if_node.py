"""
Unit tests for the IfConditionNode DAG node.

Tests routing logic, external state control, error handling, and status reporting.
"""
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from app.modules.flow_control.if_condition.node import IfConditionNode


class TestIfConditionNodeBasicRouting:
    """Test basic true/false routing logic."""
    
    @pytest.mark.asyncio
    async def test_routes_to_true_port_when_condition_true(self):
        # Setup
        manager = Mock()
        manager.downstream_map = {
            "test_if_1": [
                {"target_id": "downsample_1", "source_port": "true"},
                {"target_id": "discard_1", "source_port": "false"}
            ]
        }
        manager.forward_data = AsyncMock()
        
        node = IfConditionNode(
            manager=manager,
            node_id="test_if_1",
            name="Test IF",
            expression="point_count > 1000",
            throttle_ms=0
        )
        
        # Execute
        payload = {"point_count": 1500, "points": []}
        await node.on_input(payload)
        
        # Verify true port called, false port not called
        assert manager.forward_data.call_count == 1
        manager.forward_data.assert_called_once_with("downsample_1", payload)
    
    @pytest.mark.asyncio
    async def test_routes_to_false_port_when_condition_false(self):
        manager = Mock()
        manager.downstream_map = {
            "test_if_1": [
                {"target_id": "downsample_1", "source_port": "true"},
                {"target_id": "discard_1", "source_port": "false"}
            ]
        }
        manager.forward_data = AsyncMock()
        
        node = IfConditionNode(
            manager=manager,
            node_id="test_if_1",
            name="Test IF",
            expression="point_count > 1000",
            throttle_ms=0
        )
        
        payload = {"point_count": 500, "points": []}
        await node.on_input(payload)
        
        assert manager.forward_data.call_count == 1
        manager.forward_data.assert_called_once_with("discard_1", payload)


class TestIfConditionNodeExternalState:
    """Test external_state variable integration."""
    
    @pytest.mark.asyncio
    async def test_external_state_in_expression(self):
        manager = Mock()
        manager.downstream_map = {
            "test_if_1": [
                {"target_id": "target_true", "source_port": "true"},
                {"target_id": "target_false", "source_port": "false"}
            ]
        }
        manager.forward_data = AsyncMock()
        
        node = IfConditionNode(
            manager=manager,
            node_id="test_if_1",
            name="Test IF",
            expression="external_state == True",
            throttle_ms=0
        )
        
        # Initially false
        payload = {"points": []}
        await node.on_input(payload)
        manager.forward_data.assert_called_with("target_false", payload)
        
        # Set to true
        node.external_state = True
        manager.forward_data.reset_mock()
        await node.on_input(payload)
        manager.forward_data.assert_called_with("target_true", payload)


class TestIfConditionNodeErrorHandling:
    """Test fail-safe error handling."""
    
    @pytest.mark.asyncio
    async def test_syntax_error_routes_to_false_port(self):
        manager = Mock()
        manager.downstream_map = {
            "test_if_1": [
                {"target_id": "target_true", "source_port": "true"},
                {"target_id": "target_false", "source_port": "false"}
            ]
        }
        manager.forward_data = AsyncMock()
        
        node = IfConditionNode(
            manager=manager,
            node_id="test_if_1",
            name="Test IF",
            expression="invalid ><",  # Invalid syntax
            throttle_ms=0
        )
        
        payload = {"points": []}
        await node.on_input(payload)
        
        # Should route to false port
        manager.forward_data.assert_called_with("target_false", payload)
        
        # Should log error
        assert node.last_error is not None
        assert "syntax" in node.last_error.lower() or "error" in node.last_error.lower()
    
    @pytest.mark.asyncio
    async def test_missing_field_routes_to_false_port(self):
        manager = Mock()
        manager.downstream_map = {
            "test_if_1": [
                {"target_id": "target_true", "source_port": "true"},
                {"target_id": "target_false", "source_port": "false"}
            ]
        }
        manager.forward_data = AsyncMock()
        
        node = IfConditionNode(
            manager=manager,
            node_id="test_if_1",
            name="Test IF",
            expression="missing_field > 100",
            throttle_ms=0
        )
        
        payload = {"point_count": 1000, "points": []}
        await node.on_input(payload)
        
        # Missing field should evaluate to None, comparison fails -> false
        manager.forward_data.assert_called_with("target_false", payload)
        assert node.last_evaluation is False



class TestIfConditionNodeComplexExpressions:
    """Test complex multi-condition expressions."""
    
    @pytest.mark.asyncio
    async def test_quality_gate_expression(self):
        manager = Mock()
        manager.downstream_map = {
            "test_if_1": [
                {"target_id": "target_true", "source_port": "true"},
                {"target_id": "target_false", "source_port": "false"}
            ]
        }
        manager.forward_data = AsyncMock()
        
        node = IfConditionNode(
            manager=manager,
            node_id="test_if_1",
            name="Test IF",
            expression="point_count > 1000 AND intensity_avg >= 50 AND variance > 0.01",
            throttle_ms=0
        )
        
        # Passing payload
        payload = {
            "point_count": 5500,
            "intensity_avg": 75,
            "variance": 0.02,
            "points": []
        }
        await node.on_input(payload)
        manager.forward_data.assert_called_with("target_true", payload)
        
        # Failing payload (one condition fails)
        manager.forward_data.reset_mock()
        payload2 = {
            "point_count": 5500,
            "intensity_avg": 30,  # Below threshold
            "variance": 0.02,
            "points": []
        }
        await node.on_input(payload2)
        manager.forward_data.assert_called_with("target_false", payload2)


class TestIfConditionNodeBackwardsCompatibility:
    """Test that node works with legacy downstream_map formats."""
    
    @pytest.mark.asyncio
    async def test_works_with_empty_downstream_map(self):
        manager = Mock()
        manager.downstream_map = {}
        manager.forward_data = AsyncMock()
        
        node = IfConditionNode(
            manager=manager,
            node_id="test_if_1",
            name="Test IF",
            expression="True",
            throttle_ms=0
        )
        
        payload = {"points": []}
        # Should not crash even with no downstream nodes
        await node.on_input(payload)
        
        # forward_data should not be called
        manager.forward_data.assert_not_called()


# ---------------------------------------------------------------------------
# Task B6 — emit_status() tests
# ---------------------------------------------------------------------------

class TestIfConditionNodeEmitStatus:
    """Test IfConditionNode.emit_status() standardized status reporting."""

    @pytest.fixture
    def node(self):
        manager = Mock()
        manager.downstream_map = {}
        manager.forward_data = AsyncMock()
        return IfConditionNode(
            manager=manager,
            node_id="if-node-1",
            name="Test IF",
            expression="point_count > 1000",
        )

    def test_emit_status_no_evaluation(self, node):
        """state is None (no evaluation yet) → RUNNING, no application_state."""
        from app.schemas.status import NodeStatusUpdate, OperationalState

        node.state = None
        node.last_error = None

        status = node.emit_status()

        assert isinstance(status, NodeStatusUpdate)
        assert status.node_id == "if-node-1"
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is None
        assert status.error_message is None

    def test_emit_status_true(self, node):
        """state == True → RUNNING, condition='true', green."""
        from app.schemas.status import NodeStatusUpdate, OperationalState

        node.state = True
        node.last_error = None

        status = node.emit_status()

        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is not None
        assert status.application_state.label == "condition"
        assert status.application_state.value == "true"
        assert status.application_state.color == "green"

    def test_emit_status_false(self, node):
        """state == False → RUNNING, condition='false', red."""
        from app.schemas.status import NodeStatusUpdate, OperationalState

        node.state = False
        node.last_error = None

        status = node.emit_status()

        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is not None
        assert status.application_state.label == "condition"
        assert status.application_state.value == "false"
        assert status.application_state.color == "red"

    def test_emit_status_error(self, node):
        """last_error set → ERROR, no application_state, error_message propagated."""
        from app.schemas.status import NodeStatusUpdate, OperationalState

        node.state = False
        node.last_error = "Expression evaluation failed: syntax error"

        status = node.emit_status()

        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.ERROR
        assert status.error_message == "Expression evaluation failed: syntax error"
