"""
Integration tests for IF condition node routing in complete DAG topology.

Tests dual-port routing (true/false) with expression evaluation and external state control.
Verifies that data flows correctly through the DAG based on condition results.
"""
import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from app.modules.flow_control.if_condition.node import IfConditionNode


class TestIfNodeBasicRouting:
    """
    Test basic IF node routing in a simple DAG topology.
    DAG: Source → IfNode → [TrueTarget, FalseTarget]
    """

    @pytest.fixture
    def mock_manager(self):
        """Mock node manager with forward_data capability."""
        manager = Mock()
        manager.forward_data = AsyncMock()
        manager.downstream_map = {}
        return manager

    @pytest.fixture
    def if_node(self, mock_manager):
        """Create IF node with simple expression."""
        node = IfConditionNode(
            manager=mock_manager,
            node_id="if-1",
            name="condition_check",
            expression="point_count > 1000",
            throttle_ms=0
        )
        
        # Configure downstream nodes for dual-port routing in manager
        mock_manager.downstream_map["if-1"] = [
            {"target_id": "true-target", "source_port": "true"},
            {"target_id": "false-target", "source_port": "false"}
        ]
        
        return node

    @pytest.mark.asyncio
    async def test_true_condition_routes_to_true_port(self, if_node, mock_manager):
        """Data satisfying condition routes to true port only."""
        payload = {
            "point_count": 1500,  # > 1000, should route to true
            "points": np.random.rand(1500, 3).astype(np.float32),
            "timestamp": 1.0
        }
        
        await if_node.on_input(payload)
        
        # Should call forward_data once with the node's id and active_port='true'
        mock_manager.forward_data.assert_called_once()
        call_args = mock_manager.forward_data.call_args
        assert call_args[0][0] == "if-1"
        assert call_args.kwargs["active_port"] == "true"
        assert call_args[0][1]["point_count"] == 1500
        assert "condition_result" in call_args[0][1]
        assert call_args[0][1]["condition_result"] is True

    @pytest.mark.asyncio
    async def test_false_condition_routes_to_false_port(self, if_node, mock_manager):
        """Data not satisfying condition routes to false port only."""
        payload = {
            "point_count": 500,  # < 1000, should route to false
            "points": np.random.rand(500, 3).astype(np.float32),
            "timestamp": 2.0
        }
        
        await if_node.on_input(payload)
        
        # Should call forward_data once with the node's id and active_port='false'
        mock_manager.forward_data.assert_called_once()
        call_args = mock_manager.forward_data.call_args
        assert call_args[0][0] == "if-1"
        assert call_args.kwargs["active_port"] == "false"
        assert call_args[0][1]["point_count"] == 500
        assert call_args[0][1]["condition_result"] is False

    @pytest.mark.asyncio
    async def test_no_calls_when_no_matching_port(self, if_node, mock_manager):
        """Node with only true port configured: forward_data is still called
        once (with active_port='false'), but the router finds no matching edge.
        The node delegates filtering to the manager."""
        # Reconfigure to only have true port
        mock_manager.downstream_map["if-1"] = [{"target_id": "true-target", "source_port": "true"}]
        
        payload = {
            "point_count": 500,  # false condition
            "timestamp": 3.0
        }
        
        await if_node.on_input(payload)
        
        # forward_data is called once; the router (not the node) filters out
        # the unmatched port.  Verify the correct port is requested.
        mock_manager.forward_data.assert_called_once()
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "false"


class TestIfNodeExternalStateControl:
    """
    Test external state control via API.
    DAG: Source → IfNode(external_state) → [TrueTarget, FalseTarget]
    """

    @pytest.fixture
    def mock_manager(self):
        manager = Mock()
        manager.forward_data = AsyncMock()
        manager.downstream_map = {}
        return manager

    @pytest.fixture
    def external_state_node(self, mock_manager):
        """Create IF node with external_state condition."""
        node = IfConditionNode(
            manager=mock_manager,
            node_id="if-external",
            name="external_gate",
            expression="external_state == true",
            throttle_ms=0
        )
        
        mock_manager.downstream_map["if-external"] = [
            {"target_id": "allowed-target", "source_port": "true"},
            {"target_id": "blocked-target", "source_port": "false"}
        ]
        
        return node

    @pytest.mark.asyncio
    async def test_external_state_false_blocks_data(self, external_state_node, mock_manager):
        """With external_state=False, data routes to false port."""
        external_state_node.external_state = False
        
        payload = {"point_count": 1000, "timestamp": 1.0}
        await external_state_node.on_input(payload)
        
        # Should route via false port
        mock_manager.forward_data.assert_called_once()
        call_args = mock_manager.forward_data.call_args
        assert call_args[0][0] == "if-external"
        assert call_args.kwargs["active_port"] == "false"

    @pytest.mark.asyncio
    async def test_external_state_true_allows_data(self, external_state_node, mock_manager):
        """With external_state=True, data routes to true port."""
        external_state_node.external_state = True
        
        payload = {"point_count": 1000, "timestamp": 2.0}
        await external_state_node.on_input(payload)
        
        # Should route via true port
        mock_manager.forward_data.assert_called_once()
        call_args = mock_manager.forward_data.call_args
        assert call_args[0][0] == "if-external"
        assert call_args.kwargs["active_port"] == "true"

    @pytest.mark.asyncio
    async def test_toggling_external_state_changes_routing(self, external_state_node, mock_manager):
        """Changing external_state dynamically changes routing."""
        payload = {"point_count": 1000, "timestamp": 3.0}
        
        # First with False
        external_state_node.external_state = False
        await external_state_node.on_input(payload.copy())
        assert mock_manager.forward_data.call_count == 1
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "false"
        
        mock_manager.forward_data.reset_mock()
        
        # Then toggle to True
        external_state_node.external_state = True
        await external_state_node.on_input(payload.copy())
        assert mock_manager.forward_data.call_count == 1
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "true"


class TestIfNodeComplexExpressions:
    """
    Test IF node with complex boolean expressions.
    DAG: Source → IfNode(complex expression) → [TrueTarget, FalseTarget]
    """

    @pytest.fixture
    def mock_manager(self):
        manager = Mock()
        manager.forward_data = AsyncMock()
        manager.downstream_map = {}
        return manager

    @pytest.mark.asyncio
    async def test_compound_and_condition(self, mock_manager):
        """Test AND condition: both must be true."""
        node = IfConditionNode(
            manager=mock_manager,
            node_id="if-complex",
            name="complex_check",
            expression="point_count > 1000 AND intensity_avg > 50",
            throttle_ms=0
        )
        mock_manager.downstream_map["if-complex"] = [
            {"target_id": "true-target", "source_port": "true"},
            {"target_id": "false-target", "source_port": "false"}
        ]
        
        # Both conditions true
        payload1 = {"point_count": 1500, "intensity_avg": 75, "timestamp": 1.0}
        await node.on_input(payload1)
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "true"
        
        mock_manager.forward_data.reset_mock()
        
        # One condition false
        payload2 = {"point_count": 1500, "intensity_avg": 25, "timestamp": 2.0}
        await node.on_input(payload2)
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "false"

    @pytest.mark.asyncio
    async def test_compound_or_condition(self, mock_manager):
        """Test OR condition: at least one must be true."""
        node = IfConditionNode(
            manager=mock_manager,
            node_id="if-or",
            name="or_check",
            expression="point_count > 1000 OR intensity_avg > 50",
            throttle_ms=0
        )
        mock_manager.downstream_map["if-or"] = [
            {"target_id": "true-target", "source_port": "true"},
            {"target_id": "false-target", "source_port": "false"}
        ]
        
        # Only first condition true
        payload1 = {"point_count": 1500, "intensity_avg": 25, "timestamp": 1.0}
        await node.on_input(payload1)
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "true"
        
        mock_manager.forward_data.reset_mock()
        
        # Both conditions false
        payload2 = {"point_count": 500, "intensity_avg": 25, "timestamp": 2.0}
        await node.on_input(payload2)
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "false"

    @pytest.mark.asyncio
    async def test_parentheses_grouping(self, mock_manager):
        """Test parentheses change evaluation order."""
        node = IfConditionNode(
            manager=mock_manager,
            node_id="if-paren",
            name="parentheses_check",
            expression="(point_count > 1000 OR external_state == true) AND intensity_avg > 50",
            throttle_ms=0
        )
        mock_manager.downstream_map["if-paren"] = [
            {"target_id": "true-target", "source_port": "true"},
            {"target_id": "false-target", "source_port": "false"}
        ]
        
        # external_state true, point_count low, but intensity high → should be TRUE
        node.external_state = True
        payload = {"point_count": 500, "intensity_avg": 75, "timestamp": 1.0}
        await node.on_input(payload)
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "true"


class TestIfNodeErrorHandling:
    """
    Test IF node error handling and fail-safe routing.
    All errors should route to false port.
    """

    @pytest.fixture
    def mock_manager(self):
        manager = Mock()
        manager.forward_data = AsyncMock()
        manager.downstream_map = {}
        return manager

    @pytest.mark.asyncio
    async def test_missing_field_routes_to_false(self, mock_manager):
        """Missing fields in payload route to false port."""
        node = IfConditionNode(
            manager=mock_manager,
            node_id="if-missing",
            name="missing_field_check",
            expression="missing_field > 1000",
            throttle_ms=0
        )
        mock_manager.downstream_map["if-missing"] = [
            {"target_id": "true-target", "source_port": "true"},
            {"target_id": "false-target", "source_port": "false"}
        ]
        
        payload = {"point_count": 1500, "timestamp": 1.0}  # missing_field not present
        await node.on_input(payload)
        
        # Should route to false port (fail-safe)
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "false"
        
        # Missing field evaluates gracefully to False (no error raised by parser)
        assert node.last_error is None
        assert node.last_evaluation is False

    @pytest.mark.asyncio
    async def test_type_error_routes_to_false(self, mock_manager):
        """Type mismatches route to false port."""
        node = IfConditionNode(
            manager=mock_manager,
            node_id="if-type",
            name="type_check",
            expression="point_count > 1000",
            throttle_ms=0
        )
        mock_manager.downstream_map["if-type"] = [
            {"target_id": "true-target", "source_port": "true"},
            {"target_id": "false-target", "source_port": "false"}
        ]
        
        # point_count is a string, not a number
        payload = {"point_count": "many", "timestamp": 1.0}
        await node.on_input(payload)
        
        # Should route to false port (fail-safe)
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "false"
        assert node.last_error is not None


class TestIfNodeBackwardsCompatibility:
    """
    Test that IF node works with legacy downstream_map formats.
    Ensures old configs (string list) still function.
    """

    @pytest.fixture
    def mock_manager(self):
        manager = Mock()
        manager.forward_data = AsyncMock()
        manager.downstream_map = {}
        return manager

    @pytest.mark.asyncio
    async def test_legacy_string_downstream_map(self, mock_manager):
        """Node with string-only downstream_map: forward_data is called once.
        The manager/router handles fan-out to legacy string targets."""
        node = IfConditionNode(
            manager=mock_manager,
            node_id="if-legacy",
            name="legacy_if",
            expression="point_count > 1000",
            throttle_ms=0
        )
        
        # Legacy format: just strings, no port info
        mock_manager.downstream_map["if-legacy"] = ["target-1", "target-2"]
        
        payload = {"point_count": 1500, "timestamp": 1.0}
        await node.on_input(payload)
        
        # forward_data is called once (node delegates to manager).
        # The router is responsible for fan-out to all legacy string targets.
        mock_manager.forward_data.assert_called_once()
        assert mock_manager.forward_data.call_args[0][0] == "if-legacy"
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "true"

    @pytest.mark.asyncio
    async def test_mixed_downstream_map(self, mock_manager):
        """Node with mixed downstream_map (legacy + port-aware): forward_data
        is called once; the router handles both string and dict edge formats."""
        node = IfConditionNode(
            manager=mock_manager,
            node_id="if-mixed",
            name="mixed_if",
            expression="point_count > 1000",
            throttle_ms=0
        )
        
        # Mixed format
        mock_manager.downstream_map["if-mixed"] = [
            "legacy-target",  # old string format
            {"target_id": "true-target", "source_port": "true"},
            {"target_id": "false-target", "source_port": "false"}
        ]
        
        payload = {"point_count": 1500, "timestamp": 1.0}  # true condition
        await node.on_input(payload)
        
        # forward_data is called once; router handles filtered fan-out.
        mock_manager.forward_data.assert_called_once()
        assert mock_manager.forward_data.call_args[0][0] == "if-mixed"
        assert mock_manager.forward_data.call_args.kwargs["active_port"] == "true"


class TestIfNodeMetadataEnrichment:
    """
    Test that IF node adds condition result to payload metadata.
    """

    @pytest.fixture
    def mock_manager(self):
        manager = Mock()
        manager.forward_data = AsyncMock()
        manager.downstream_map = {}
        return manager

    @pytest.fixture
    def if_node(self, mock_manager):
        node = IfConditionNode(
            manager=mock_manager,
            node_id="if-meta",
            name="metadata_if",
            expression="point_count > 1000",
            throttle_ms=0
        )
        mock_manager.downstream_map["if-meta"] = [{"target_id": "target", "source_port": "true"}]
        return node

    @pytest.mark.asyncio
    async def test_condition_result_added_to_payload(self, if_node, mock_manager):
        """Payload includes condition_result field after evaluation."""
        payload = {"point_count": 1500, "timestamp": 1.0}
        await if_node.on_input(payload)
        
        forwarded_payload = mock_manager.forward_data.call_args[0][1]
        assert "condition_result" in forwarded_payload
        assert forwarded_payload["condition_result"] is True

    @pytest.mark.asyncio
    async def test_original_payload_preserved(self, if_node, mock_manager):
        """Original payload fields are preserved."""
        payload = {"point_count": 1500, "custom_field": "test", "timestamp": 1.0}
        await if_node.on_input(payload)
        
        forwarded_payload = mock_manager.forward_data.call_args[0][1]
        assert forwarded_payload["point_count"] == 1500
        assert forwarded_payload["custom_field"] == "test"
        assert forwarded_payload["timestamp"] == 1.0
