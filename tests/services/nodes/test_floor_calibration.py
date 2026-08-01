"""Unit tests for the shared FloorCalibrationMixin."""
import math

import numpy as np
import pytest

from app.schemas.pose import Pose
from app.services.nodes.floor_calibration import FloorCalibrationMixin


class _FakeNode(FloorCalibrationMixin):
    """Minimal host satisfying the mixin contract, without DB persistence."""

    def __init__(self, pose: Pose = Pose.zero(), imu_auto_level: bool = False):
        self.id = "fake-node"
        self.pose_params = pose
        self.imu_auto_level = imu_auto_level
        self.set_pose_calls: list[Pose] = []

    def set_pose(self, pose: Pose):
        self.pose_params = pose
        self.set_pose_calls.append(pose)
        return self


def _tilted_floor_cloud(roll_deg: float, pitch_deg: float, n: int = 2000) -> np.ndarray:
    """Generate a dense planar cloud tilted by the given roll/pitch."""
    rng = np.random.default_rng(0)
    xy = (rng.random((n, 2)) - 0.5) * 10.0
    flat = np.column_stack([xy, np.zeros(n)])
    r, p = math.radians(roll_deg), math.radians(pitch_deg)
    Rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    Ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
    return flat @ (Ry @ Rx).T


@pytest.fixture(autouse=True)
def _no_db_persist(monkeypatch):
    """Stub out DB persistence so the mixin can run in isolation."""
    from app.repositories import node_orm

    monkeypatch.setattr(node_orm.NodeRepository, "update_node_pose", lambda self, *a, **k: None)


def test_raises_when_no_frame_cached():
    node = _FakeNode()
    with pytest.raises(ValueError, match="No point-cloud frame"):
        node.calibrate_from_floor()


def test_raises_when_imu_auto_level_enabled():
    node = _FakeNode(imu_auto_level=True)
    node.cache_floor_frame(_tilted_floor_cloud(0, 0))
    with pytest.raises(ValueError, match="IMU auto-level"):
        node.calibrate_from_floor()


def test_raises_when_no_horizontal_plane():
    node = _FakeNode()
    # A vertical wall (normal in XY plane) should be rejected.
    wall = _tilted_floor_cloud(90.0, 0.0)
    node.cache_floor_frame(wall)
    with pytest.raises(ValueError, match="No floor-like"):
        node.calibrate_from_floor()


def test_levels_a_tilted_floor():
    node = _FakeNode()
    node.cache_floor_frame(_tilted_floor_cloud(6.0, -4.0))
    new_pose = node.calibrate_from_floor()
    # Residual correction should oppose the tilt and land within a degree.
    assert abs(new_pose.roll - (-6.0)) < 1.0
    assert abs(new_pose.pitch - 4.0) < 1.0


def test_flat_floor_needs_no_correction():
    node = _FakeNode()
    node.cache_floor_frame(_tilted_floor_cloud(0.0, 0.0))
    new_pose = node.calibrate_from_floor()
    assert abs(new_pose.roll) < 0.5
    assert abs(new_pose.pitch) < 0.5
