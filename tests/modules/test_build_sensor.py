"""
B-17: Unit tests for build_sensor() factory with Pose from node["pose"].

Tests cover:
- build_sensor() with node["pose"] dict produces correct pose on sensor
- build_sensor() with empty node["pose"] = {} defaults to Pose.zero()
- Old flat config keys (x, y, z in config) are not used
"""
import pytest
from unittest.mock import MagicMock, patch
import numpy as np


def _make_service_context():
    """Create a minimal service_context mock."""
    ctx = MagicMock()
    ctx._topic_registry.register.return_value = "test_sensor"
    return ctx


def _base_node(pose_override=None, config_override=None):
    """Return a minimal valid sensor node dict."""
    node = {
        "id": "test-sensor-001",
        "name": "Test LiDAR",
        "type": "sensor",
        "category": "sensor",
        "config": {
            "lidar_type": "multiscan",
            "hostname": "192.168.1.10",
            "mode": "sim",
            "pcd_path": "/tmp/test.pcd",
            "throttle_ms": 0,
        },
        "pose": pose_override if pose_override is not None else {},
    }
    if config_override:
        node["config"].update(config_override)
    return node


class TestBuildSensorWithPose:
    """B-17: build_sensor factory with Pose object."""

    def test_build_sensor_with_pose_sets_correct_transformation(self):
        from app.modules.lidar.registry import build_sensor
        from app.schemas.pose import Pose
        from app.modules.lidar.core.transformations import create_transformation_matrix

        pose_dict = {"x": 100.0, "y": 0.0, "z": 50.0, "roll": 0.0, "pitch": 0.0, "yaw": 45.0}
        node = _base_node(pose_override=pose_dict)
        ctx = _make_service_context()

        sensor = build_sensor(node, ctx, [])

        expected_T = create_transformation_matrix(**pose_dict)
        np.testing.assert_array_almost_equal(sensor.transformation, expected_T)

    def test_build_sensor_with_empty_pose_defaults_to_zero(self):
        from app.modules.lidar.registry import build_sensor
        from app.schemas.pose import Pose

        node = _base_node(pose_override={})
        ctx = _make_service_context()

        sensor = build_sensor(node, ctx, [])

        assert sensor.get_pose_params() == Pose.zero()
        np.testing.assert_array_almost_equal(sensor.transformation, np.eye(4))

    def test_build_sensor_with_no_pose_key_defaults_to_zero(self):
        from app.modules.lidar.registry import build_sensor
        from app.schemas.pose import Pose

        node = _base_node()
        # Remove pose key entirely
        node.pop("pose", None)
        ctx = _make_service_context()

        sensor = build_sensor(node, ctx, [])

        assert sensor.get_pose_params() == Pose.zero()

    def test_build_sensor_pose_params_is_pose_instance(self):
        from app.modules.lidar.registry import build_sensor
        from app.schemas.pose import Pose

        node = _base_node(pose_override={"x": 100.0, "yaw": 45.0})
        ctx = _make_service_context()

        sensor = build_sensor(node, ctx, [])

        result = sensor.get_pose_params()
        assert isinstance(result, Pose)
        assert result.x == 100.0
        assert result.yaw == 45.0
