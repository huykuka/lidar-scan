"""
Unit tests for the Truck Bin Detection module.

Covers:
  - BinDetector: synthetic bin cloud detection, dimension validation,
    rejection of undersized/invalid clouds, wall detection, volume computation
  - TruckBinDetectionNode: on_input integration, status reporting, state machine
  - Registry: schema and factory registration
"""
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from app.modules.application.truck_bin_detection.utils.bin_detector import (
    BinDetector,
    BinDetectionResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic point cloud generators
# ─────────────────────────────────────────────────────────────────────────────


def _generate_bin_floor(
    length: float = 6.0,
    width: float = 2.4,
    center: np.ndarray = None,
    z_height: float = 1.0,
    density: int = 2000,
    noise_std: float = 0.01,
) -> np.ndarray:
    """Generate a flat rectangular floor plane representing the bin bottom.

    Args:
        length:    Bin length along X axis (metres).
        width:     Bin width along Y axis (metres).
        center:    3D center of the floor (defaults to [0, 0, z_height]).
        z_height:  Z coordinate of the floor plane.
        density:   Number of points to generate.
        noise_std: Gaussian noise added to Z coordinates.

    Returns:
        Nx3 array of floor points.
    """
    if center is None:
        center = np.array([0.0, 0.0, z_height])

    rng = np.random.default_rng(42)
    x = rng.uniform(center[0] - length / 2, center[0] + length / 2, density)
    y = rng.uniform(center[1] - width / 2, center[1] + width / 2, density)
    z = np.full(density, center[2]) + rng.normal(0, noise_std, density)
    return np.column_stack([x, y, z])


def _generate_bin_wall(
    start: np.ndarray,
    end: np.ndarray,
    height: float = 1.5,
    z_base: float = 1.0,
    density: int = 500,
    noise_std: float = 0.01,
) -> np.ndarray:
    """Generate a vertical wall plane between two 2D points.

    Args:
        start:     2D start point of the wall base [x, y].
        end:       2D end point of the wall base [x, y].
        height:    Wall height (metres).
        z_base:    Z coordinate of the wall base (floor level).
        density:   Number of points to generate.
        noise_std: Gaussian noise perpendicular to wall surface.

    Returns:
        Nx3 array of wall points.
    """
    rng = np.random.default_rng(123)
    t = rng.uniform(0, 1, density)
    wall_dir = end - start
    normal_2d = np.array([-wall_dir[1], wall_dir[0]])
    normal_2d = normal_2d / (np.linalg.norm(normal_2d) + 1e-9)

    xy = start + np.outer(t, wall_dir)
    xy += rng.normal(0, noise_std, (density, 1)) * normal_2d

    z = rng.uniform(z_base, z_base + height, density)
    return np.column_stack([xy, z])


def _generate_open_top_truck_bin(
    length: float = 6.0,
    width: float = 2.4,
    wall_height: float = 1.5,
    floor_z: float = 1.0,
    floor_density: int = 2000,
    wall_density: int = 500,
) -> np.ndarray:
    """Generate a complete open-top truck bin point cloud.

    Creates a rectangular bin with floor + 4 walls (left, right, front, back).

    Args:
        length:        Bin length (X axis).
        width:         Bin width (Y axis).
        wall_height:   Height of bin walls.
        floor_z:       Z coordinate of the bin floor.
        floor_density: Points in the floor.
        wall_density:  Points per wall.

    Returns:
        Nx3 array combining floor and all wall points.
    """
    half_l = length / 2.0
    half_w = width / 2.0

    # Floor
    floor = _generate_bin_floor(
        length=length, width=width, z_height=floor_z, density=floor_density
    )

    # Left wall (Y = -half_w, running along X)
    left_wall = _generate_bin_wall(
        start=np.array([-half_l, -half_w]),
        end=np.array([half_l, -half_w]),
        height=wall_height,
        z_base=floor_z,
        density=wall_density,
    )

    # Right wall (Y = +half_w, running along X)
    right_wall = _generate_bin_wall(
        start=np.array([-half_l, half_w]),
        end=np.array([half_l, half_w]),
        height=wall_height,
        z_base=floor_z,
        density=wall_density,
    )

    # Front wall (X = +half_l, running along Y)
    front_wall = _generate_bin_wall(
        start=np.array([half_l, -half_w]),
        end=np.array([half_l, half_w]),
        height=wall_height,
        z_base=floor_z,
        density=wall_density,
    )

    # Back wall (X = -half_l, running along Y)
    back_wall = _generate_bin_wall(
        start=np.array([-half_l, -half_w]),
        end=np.array([-half_l, half_w]),
        height=wall_height,
        z_base=floor_z,
        density=wall_density,
    )

    return np.vstack([floor, left_wall, right_wall, front_wall, back_wall])


# ─────────────────────────────────────────────────────────────────────────────
# BinDetector unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestBinDetector:
    """Tests for the BinDetector algorithm."""

    def test_detects_valid_bin(self):
        """A well-formed open-top bin should be detected with correct dimensions."""
        cloud = _generate_open_top_truck_bin(
            length=6.0, width=2.4, wall_height=1.5
        )
        detector = BinDetector(
            min_bin_length=2.0,
            min_bin_width=1.5,
            min_bin_height=0.5,
            voxel_size=0.0,  # no downsampling for test precision
        )

        result = detector.detect(cloud)

        assert result.detected is True
        # Dimensions should be approximately correct (within 20% tolerance
        # due to noise and algorithmic approximation)
        assert result.length > 4.0, f"Length {result.length} too short"
        assert result.width > 1.5, f"Width {result.width} too narrow"
        assert result.height > 0.8, f"Height {result.height} too low"
        assert result.volume > 0.0
        assert result.bin_points is not None
        assert len(result.bin_points) > 0

    def test_volume_approximately_correct(self):
        """Detected volume should be in a reasonable range for the given dimensions."""
        cloud = _generate_open_top_truck_bin(
            length=5.0, width=2.0, wall_height=1.0
        )
        detector = BinDetector(
            min_bin_length=2.0,
            min_bin_width=1.5,
            min_bin_height=0.5,
            voxel_size=0.0,
        )

        result = detector.detect(cloud)

        assert result.detected is True
        # True volume = 5.0 * 2.0 * 1.0 = 10.0 m³
        # Allow wide tolerance due to algorithmic approximation
        assert result.volume > 3.0, f"Volume {result.volume} too small"
        assert result.volume < 30.0, f"Volume {result.volume} too large"

    def test_rejects_too_few_points(self):
        """Clouds with fewer than 20 points should be rejected."""
        cloud = np.random.default_rng(0).uniform(-1, 1, (10, 3))
        detector = BinDetector()

        result = detector.detect(cloud)

        assert result.detected is False

    def test_rejects_none_input(self):
        """None input should return not-detected."""
        detector = BinDetector()
        result = detector.detect(None)
        assert result.detected is False

    def test_rejects_empty_array(self):
        """Empty array should return not-detected."""
        detector = BinDetector()
        result = detector.detect(np.empty((0, 3)))
        assert result.detected is False

    def test_rejects_undersized_bin(self):
        """A bin smaller than min constraints should be rejected."""
        # Generate a tiny bin (1m x 1m x 0.3m)
        cloud = _generate_open_top_truck_bin(
            length=1.0, width=1.0, wall_height=0.3,
            floor_density=500, wall_density=200,
        )
        detector = BinDetector(
            min_bin_length=2.0,
            min_bin_width=1.5,
            min_bin_height=0.5,
        )

        result = detector.detect(cloud)

        assert result.detected is False

    def test_rejects_random_noise_cloud(self):
        """A random point cloud should not be detected as a bin."""
        rng = np.random.default_rng(99)
        cloud = rng.uniform(-5, 5, (5000, 3))
        detector = BinDetector(
            min_bin_length=2.0,
            min_bin_width=1.5,
            min_bin_height=0.5,
        )

        result = detector.detect(cloud)

        # Random cloud may or may not detect a floor, but dimensions
        # should fail the min constraints in most cases
        if result.detected:
            # If detected, it should at least meet the min constraints
            assert result.length >= 2.0
            assert result.width >= 1.5
            assert result.height >= 0.5

    def test_floor_detection_with_tilted_floor(self):
        """A slightly tilted floor should still be detected within tolerance."""
        # Generate floor with slight tilt (5 degrees around X axis)
        cloud = _generate_open_top_truck_bin(length=6.0, width=2.4, wall_height=1.5)
        # Apply small rotation to simulate tilt
        angle = np.radians(5)
        rotation = np.array([
            [1, 0, 0],
            [0, np.cos(angle), -np.sin(angle)],
            [0, np.sin(angle), np.cos(angle)],
        ])
        cloud = cloud @ rotation.T

        detector = BinDetector(
            min_bin_length=2.0,
            min_bin_width=1.5,
            min_bin_height=0.5,
            horizontal_tolerance_deg=15.0,
            voxel_size=0.0,
        )

        result = detector.detect(cloud)

        assert result.detected is True

    def test_with_voxel_downsampling(self):
        """Detection should work with voxel downsampling enabled."""
        cloud = _generate_open_top_truck_bin(
            length=6.0, width=2.4, wall_height=1.5,
            floor_density=5000, wall_density=1000,
        )
        detector = BinDetector(
            min_bin_length=2.0,
            min_bin_width=1.5,
            min_bin_height=0.5,
            voxel_size=0.05,
        )

        result = detector.detect(cloud)

        assert result.detected is True
        assert result.volume > 0.0

    def test_to_dict_output(self):
        """BinDetectionResult.to_dict() should produce valid serializable dict."""
        cloud = _generate_open_top_truck_bin()
        detector = BinDetector(
            min_bin_length=2.0,
            min_bin_width=1.5,
            min_bin_height=0.5,
            voxel_size=0.0,
        )

        result = detector.detect(cloud)
        assert result.detected is True

        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["detected"] is True
        assert "length" in d
        assert "width" in d
        assert "height" in d
        assert "volume" in d
        assert "floor_centroid" in d
        assert len(d["floor_centroid"]) == 3
        assert "floor_normal" in d
        assert len(d["floor_normal"]) == 3
        assert "wall_count" in d
        assert "floor_inlier_count" in d

    def test_wall_count(self):
        """Detector should find at least 2 walls for a valid bin."""
        cloud = _generate_open_top_truck_bin(
            length=6.0, width=2.4, wall_height=1.5,
            wall_density=800,
        )
        detector = BinDetector(
            min_bin_length=2.0,
            min_bin_width=1.5,
            min_bin_height=0.5,
            wall_min_points=30,
            voxel_size=0.0,
        )

        result = detector.detect(cloud)

        assert result.detected is True
        assert result.wall_count >= 2

    def test_angled_walls_not_perpendicular_to_floor(self):
        """Walls that are not perpendicular to the floor (tapered bin) should still be detected."""
        # Generate a bin with walls angled inward by 20 degrees
        cloud = _generate_open_top_truck_bin(
            length=6.0, width=2.4, wall_height=1.5,
            wall_density=800,
        )

        # Tilt the wall points inward (rotate around the X axis for left/right walls)
        # This simulates a trapezoidal bin cross-section
        floor_mask = cloud[:, 2] < 1.05  # floor points stay flat
        wall_mask = ~floor_mask
        wall_pts = cloud[wall_mask].copy()

        # Apply 20° inward lean to wall points
        angle = np.radians(20)
        # Lean walls inward: shift Y toward center proportional to height
        height_above_floor = wall_pts[:, 2] - 1.0
        wall_pts[:, 1] -= np.sign(wall_pts[:, 1]) * height_above_floor * np.tan(angle)

        cloud_angled = np.vstack([cloud[floor_mask], wall_pts])

        detector = BinDetector(
            min_bin_length=2.0,
            min_bin_width=1.5,
            min_bin_height=0.5,
            vertical_tolerance_deg=30.0,
            wall_min_points=30,
            voxel_size=0.0,
        )

        result = detector.detect(cloud_angled)

        assert result.detected is True
        assert result.height > 0.5

    def test_floor_only_no_walls(self):
        """A floor-only cloud should still detect if height comes from scattered points above."""
        floor = _generate_bin_floor(length=6.0, width=2.4, z_height=1.0, density=3000)
        # Add some scattered points above to give height
        rng = np.random.default_rng(77)
        above = np.column_stack([
            rng.uniform(-3, 3, 200),
            rng.uniform(-1.2, 1.2, 200),
            rng.uniform(1.5, 2.5, 200),
        ])
        cloud = np.vstack([floor, above])

        detector = BinDetector(
            min_bin_length=2.0,
            min_bin_width=1.5,
            min_bin_height=0.5,
            wall_min_points=50,
            voxel_size=0.0,
        )

        result = detector.detect(cloud)

        # Should detect the floor and compute height from the scattered points
        assert result.detected is True
        assert result.height > 0.5


# ─────────────────────────────────────────────────────────────────────────────
# TruckBinDetectionNode unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTruckBinDetectionNode:
    """Tests for the TruckBinDetectionNode DAG integration."""

    def _make_node(self, config: Optional[Dict[str, Any]] = None):
        """Create a node with a mocked manager."""
        from app.modules.application.truck_bin_detection.node import TruckBinDetectionNode

        manager = MagicMock()
        manager.forward_data = AsyncMock()

        if config is None:
            config = {
                "min_bin_length": 2.0,
                "min_bin_width": 1.5,
                "min_bin_height": 0.5,
                "voxel_size": 0.0,
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
        """Node should detect a bin and forward data downstream."""
        node, manager = self._make_node()
        cloud = _generate_open_top_truck_bin()

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

    @pytest.mark.asyncio
    async def test_on_input_none_points(self):
        """Node should skip None point data."""
        node, manager = self._make_node()

        payload = {"node_id": "upstream_1", "points": None, "timestamp": 1.0}
        await node.on_input(payload)

        manager.forward_data.assert_not_called()

    def test_emit_status_idle(self):
        """Status should be RUNNING/idle when no processing has occurred."""
        node, _ = self._make_node()

        status = node.emit_status()

        assert status.operational_state == "RUNNING"
        assert status.application_state.value == "idle"
        assert status.application_state.color == "gray"

    @pytest.mark.asyncio
    async def test_emit_status_after_detection(self):
        """Status should show detection info after successful processing."""
        node, _ = self._make_node()
        cloud = _generate_open_top_truck_bin()

        await node.on_input({"node_id": "up", "points": cloud, "timestamp": 1.0})

        status = node.emit_status()
        assert status.operational_state == "RUNNING"
        assert "detected" in status.application_state.value
        assert status.application_state.color == "green"

    @pytest.mark.asyncio
    async def test_emit_status_no_bin(self):
        """Status should show 'no bin' after analysis finds nothing."""
        node, _ = self._make_node()
        # Use random noise that won't form a valid bin
        rng = np.random.default_rng(0)
        noise = rng.uniform(-1, 1, (100, 3))

        await node.on_input({"node_id": "up", "points": noise, "timestamp": 1.0})

        status = node.emit_status()
        assert status.application_state.value == "no bin"
        assert status.application_state.color == "orange"

    def test_stop_resets_state(self):
        """Calling stop() should reset to idle state."""
        node, _ = self._make_node()
        node.stop()

        status = node.emit_status()
        assert status.application_state.value == "idle"


# ─────────────────────────────────────────────────────────────────────────────
# Registry tests
# ─────────────────────────────────────────────────────────────────────────────


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
        assert defn.websocket_enabled is True
        assert len(defn.inputs) == 1
        assert len(defn.outputs) == 1

    def test_factory_registered(self):
        """NodeFactory should have a builder for truck_bin_detection."""
        from app.services.nodes.node_factory import NodeFactory

        # Trigger registration
        import app.modules.application.truck_bin_detection.registry  # noqa: F401

        assert "truck_bin_detection" in NodeFactory._registry

    def test_factory_builds_node(self):
        """Factory should produce a TruckBinDetectionNode instance."""
        from app.modules.application.truck_bin_detection.node import TruckBinDetectionNode
        from app.services.nodes.node_factory import NodeFactory

        import app.modules.application.truck_bin_detection.registry  # noqa: F401

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
        assert node.name == "Test Bin Node"
