"""
Unit tests for OperationNode.emit_status() standardized status reporting (Task B7).
"""
import time
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.modules.pipeline.operation_node import OperationNode
from app.schemas.status import NodeStatusUpdate, OperationalState


@pytest.fixture
def mock_manager():
    manager = Mock()
    manager.forward_data = AsyncMock()
    return manager


@pytest.fixture
def op_node(mock_manager):
    """Create an OperationNode with a mocked voxel-downsample operation."""
    mock_op_class = Mock(return_value=Mock())
    with patch.dict("app.modules.pipeline.operation_node._OP_MAP", {"voxel_downsample": mock_op_class}):
        node = OperationNode(
            manager=mock_manager,
            node_id="op-node-1",
            op_type="voxel_downsample",
            op_config={"voxel_size": 0.1},
            name="Test Downsample",
        )
    return node


class TestOperationNodeEmitStatus:
    """Test OperationNode.emit_status() standardized status reporting."""

    def test_emit_status_idle(self, op_node):
        """No input ever received → RUNNING, processing=False, gray."""
        op_node.last_input_at = None
        op_node.last_error = None

        status = op_node.emit_status()

        assert isinstance(status, NodeStatusUpdate)
        assert status.node_id == "op-node-1"
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is not None
        assert status.application_state.label == "processing"
        assert status.application_state.value is False
        assert status.application_state.color == "gray"
        assert status.error_message is None

    def test_emit_status_processing(self, op_node):
        """Recent input (< 5 s ago) → RUNNING, processing=True, blue."""
        op_node.last_input_at = time.time() - 0.5  # 0.5 s ago
        op_node.last_error = None

        status = op_node.emit_status()

        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state.value is True
        assert status.application_state.color == "blue"

    def test_emit_status_stale_input(self, op_node):
        """Last input > 5 s ago → RUNNING, processing=False, gray."""
        op_node.last_input_at = time.time() - 10.0  # 10 s ago
        op_node.last_error = None

        status = op_node.emit_status()

        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state.value is False
        assert status.application_state.color == "gray"

    def test_emit_status_error(self, op_node):
        """last_error set → ERROR, processing=False, gray, error_message propagated."""
        op_node.last_error = "Open3D segfault in voxel downsample"
        op_node.last_input_at = time.time()  # recent, but error takes priority

        status = op_node.emit_status()

        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.ERROR
        assert status.application_state.value is False
        assert status.application_state.color == "gray"
        assert status.error_message == "Open3D segfault in voxel downsample"
