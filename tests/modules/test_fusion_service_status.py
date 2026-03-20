"""
Unit tests for FusionService.emit_status() standardized status reporting (Task B8).
"""
import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock

from app.modules.fusion.service import FusionService
from app.schemas.status import NodeStatusUpdate, OperationalState


@pytest.fixture
def mock_manager():
    manager = Mock()
    manager.forward_data = AsyncMock()
    manager.nodes = {}
    return manager


@pytest.fixture
def fusion_node(mock_manager):
    return FusionService(
        node_manager=mock_manager,
        fusion_id="fusion-node-1",
    )


class TestFusionServiceEmitStatus:
    """Test FusionService.emit_status() standardized status reporting."""

    def test_emit_status_disabled(self, fusion_node):
        """Node disabled → STOPPED, fusing=0, gray."""
        fusion_node._enabled = False
        fusion_node.last_error = None

        status = fusion_node.emit_status()

        assert isinstance(status, NodeStatusUpdate)
        assert status.node_id == "fusion-node-1"
        assert status.operational_state == OperationalState.STOPPED
        assert status.application_state is not None
        assert status.application_state.label == "fusing"
        assert status.application_state.value == 0
        assert status.application_state.color == "gray"
        assert status.error_message is None

    def test_emit_status_no_inputs(self, fusion_node):
        """Node enabled, no frames received → RUNNING, fusing=0, gray."""
        fusion_node._enabled = True
        fusion_node._latest_frames = {}
        fusion_node.last_error = None

        status = fusion_node.emit_status()

        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state.value == 0
        assert status.application_state.color == "gray"

    def test_emit_status_with_inputs(self, fusion_node):
        """Node enabled with 3 sensor frames → RUNNING, fusing=3, blue."""
        fusion_node._enabled = True
        fusion_node._latest_frames = {
            "sensor-A": np.zeros((100, 3)),
            "sensor-B": np.zeros((100, 3)),
            "sensor-C": np.zeros((100, 3)),
        }
        fusion_node.last_error = None

        status = fusion_node.emit_status()

        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state.label == "fusing"
        assert status.application_state.value == 3
        assert status.application_state.color == "blue"

    def test_emit_status_error(self, fusion_node):
        """last_error set → ERROR, fusing=0, red, error_message propagated."""
        fusion_node._enabled = True
        fusion_node._latest_frames = {"sensor-A": np.zeros((100, 3))}
        fusion_node.last_error = "Column mismatch during concatenation"

        status = fusion_node.emit_status()

        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.ERROR
        assert status.application_state.value == 0
        assert status.application_state.color == "red"
        assert status.error_message == "Column mismatch during concatenation"
