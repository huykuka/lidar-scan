"""
Unit tests for the newly optimized 1D Longitudinal Profile Truck Bin Detection module.
"""
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from app.modules.application.truck_bin_detection.utils.bin_detector import (
    BinDetector,
    BinDetectionResult,
)


def _generate_synthetic_bin(
    length: float = 6.0,
    floor_z: float = 1.0,
    wall_height: float = 1.5,
) -> np.ndarray:
    """Generate a clean synthetic bin profile.

    Features a back wall, long empty body (floor), and a front wall.
    """
    half_l = length / 2.0
    pts = []
    # Rear wall at x = -half_l
    for z in np.linspace(floor_z, floor_z + wall_height, 100):
        for y in np.linspace(-1.0, 1.0, 10):
            pts.append([-half_l, y, z])
            
    # Lòng thùng (floor) at Z = 1.0
    for x in np.linspace(-half_l + 0.05, half_l - 0.05, 200):
        for y in np.linspace(-1.0, 1.0, 10):
            pts.append([x, y, floor_z])
            
    # Front wall at x = half_l
    for z in np.linspace(floor_z, floor_z + wall_height, 100):
        for y in np.linspace(-1.0, 1.0, 10):
            pts.append([half_l, y, z])
            
    return np.array(pts)


class TestBinDetector:
    """Tests for the newly optimized BinDetector 1D profile algorithm."""

    def test_detects_valid_bin_cavity(self):
        """A well-formed open-top bin should have its internal edges located properly."""
        cloud = _generate_synthetic_bin(length=6.0, floor_z=1.0, wall_height=1.5)
        
        # Upper walls are above 2.0m, cavity floor is at 1.0m (below 1.8m)
        detector = BinDetector(
            lane_width=1.2,
            z_min=1.5,
            z_max=3.0,
            bin_size=0.07,
            z_wall_threshold=2.2,
            z_cavity_max=1.8,
            min_bin_length=3.0,
            max_bin_length=8.5,
        )

        result = detector.detect(cloud)

        assert result.detected is True
        assert result.x_rear_internal < -2.5
        assert result.x_front_internal > 2.5
        assert result.length > 5.0
        assert abs(result.x_center) < 0.2
        assert result.bin_points is not None

    def test_rejects_too_few_points(self):
        """Clouds with fewer than 20 points should be rejected immediately."""
        cloud = np.random.default_rng(0).uniform(-1, 1, (10, 3))
        detector = BinDetector()

        result = detector.detect(cloud)

        assert result.detected is False

    def test_rejects_none_input(self):
        """None input should return not-detected status."""
        detector = BinDetector()
        result = detector.detect(None)
        assert result.detected is False

    def test_rejects_invalid_length_bin(self):
        """A bin with length outside configured limits should be rejected."""
        # Generate a tiny bin of 1.5m length
        cloud = _generate_synthetic_bin(length=1.5, floor_z=1.0, wall_height=1.5)
        detector = BinDetector(
            lane_width=1.2,
            z_min=1.5,
            z_max=3.0,
            bin_size=0.07,
            z_wall_threshold=2.2,
            z_cavity_max=1.8,
            min_bin_length=3.0,  # 1.5m is smaller than 3.0m limit
        )

        result = detector.detect(cloud)

        assert result.detected is False


class TestTruckBinDetectionNode:
    """Tests for the TruckBinDetectionNode DAG integration."""

    def _make_node(self, config: Optional[Dict[str, Any]] = None):
        """Create a node with a mocked manager."""
        from app.modules.application.truck_bin_detection.node import TruckBinDetectionNode

        manager = MagicMock()
        manager.forward_data = AsyncMock()

        if config is None:
            config = {
                "lane_width": 1.2,
                "z_min": 1.5,
                "z_max": 3.0,
                "bin_size": 0.07,
                "z_wall_threshold": 2.2,
                "z_cavity_max": 1.8,
                "min_bin_length": 3.0,
                "max_bin_length": 8.5,
                "target_x": 0.0,
                "tolerance": 0.2,
                "stable_duration": 0.5,
            }

        node = TruckBinDetectionNode(
            manager=manager,
            node_id="test_bin_detect_1",
            name="Test Bin Detection",
            config=config,
        )
        node._ws_topic = "node/test_bin_detect_1"
        return node, manager

    @pytest.mark.asyncio
    async def test_on_input_detects_bin(self):
        """Node should process valid input, compute errors, list status, and forward data downstream."""
        node, manager = self._make_node()
        cloud = _generate_synthetic_bin()

        payload = {
            "node_id": "upstream_1",
            "points": cloud,
            "timestamp": 1000.0,
        }

        await node.on_input(payload)

        # Should have forwarded data downstream
        manager.forward_data.assert_called_once()
        call_args = manager.forward_data.call_args
        assert call_args[0][0] == "test_bin_detect_1"
        out_payload = call_args[0][1]
        assert out_payload["node_id"] == "test_bin_detect_1"
        assert out_payload["points"] is not None
        assert "metadata" in out_payload
        assert out_payload["metadata"]["bin"]["detected"] is True

    @pytest.mark.asyncio
    async def test_on_input_empty_cloud(self):
        """Node should skip empty point clouds."""
        node, manager = self._make_node()

        payload = {"node_id": "upstream_1", "points": np.empty((0, 3)), "timestamp": 1.0}
        await node.on_input(payload)

        manager.forward_data.assert_not_called()

    def test_emit_status_idle(self):
        """Status should be idle when node has not processed any input yet."""
        node, _ = self._make_node()

        status = node.emit_status()

        assert status.operational_state == "RUNNING"
        assert status.application_state.value == "idle"
        assert status.application_state.color == "gray"


class TestTruckBinDetectionRegistry:
    """Tests for node registry and factory."""

    def test_schema_registered(self):
        """truck_bin_detection should be in the schema registry."""
        from app.services.nodes.schema import node_schema_registry

        # Trigger registration
        import app.modules.application.truck_bin_detection.registry  # noqa: F401

        defn = node_schema_registry.get("truck_bin_detection")
        assert defn is not None
        assert defn.display_name == "Truck Bin Detection"
        assert defn.category == "application"

    def test_factory_registered(self):
        """NodeFactory should have a builder for truck_bin_detection and trigger instance building."""
        from app.services.nodes.node_factory import NodeFactory
        from app.modules.application.truck_bin_detection.node import TruckBinDetectionNode

        # Trigger registration
        import app.modules.application.truck_bin_detection.registry  # noqa: F401

        assert "truck_bin_detection" in NodeFactory._registry

        node_record = {
            "id": "test_node_99",
            "name": "Test Bin Node",
            "type": "truck_bin_detection",
            "config": {"min_bin_length": 3.0},
        }
        mock_manager = MagicMock()

        node = NodeFactory.create(node_record, mock_manager, [])

        assert isinstance(node, TruckBinDetectionNode)
        assert node.id == "test_node_99"
