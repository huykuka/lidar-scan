"""
B-16: Unit tests for LidarSensor.set_pose() and get_pose_params() with Pose object.

Tests cover:
- set_pose(Pose) builds correct transformation matrix
- get_pose_params() returns Pose instance (not dict)
- set_pose() returns self (fluent interface)
"""
import numpy as np
import pytest


class TestLidarSensorSetPose:
    """B-16: LidarSensor.set_pose() accepts Pose object."""

    def _make_sensor(self):
        """Create a minimal LidarSensor for testing without hardware deps."""
        from unittest.mock import MagicMock
        from app.modules.lidar.node import LidarSensor

        manager = MagicMock()
        sensor = LidarSensor(
            manager=manager,
            sensor_id="test-sensor",
            launch_args="",
        )
        return sensor

    def test_set_pose_returns_self(self):
        from app.schemas.pose import Pose
        sensor = self._make_sensor()
        pose = Pose(x=100.0, yaw=45.0)
        result = sensor.set_pose(pose)
        assert result is sensor

    def test_set_pose_updates_transformation_matrix(self):
        from app.schemas.pose import Pose
        from app.modules.lidar.core.transformations import create_transformation_matrix

        sensor = self._make_sensor()
        pose = Pose(x=100.0, y=0.0, z=50.0, roll=0.0, pitch=0.0, yaw=45.0)
        sensor.set_pose(pose)

        expected = create_transformation_matrix(**pose.to_flat_dict())
        np.testing.assert_array_almost_equal(sensor.transformation, expected)

    def test_set_pose_updates_pose_params_as_pose(self):
        from app.schemas.pose import Pose
        sensor = self._make_sensor()
        pose = Pose(x=100.0, yaw=45.0)
        sensor.set_pose(pose)

        # pose_params must now be typed as Pose
        from app.schemas.pose import Pose as PoseClass
        assert isinstance(sensor.pose_params, PoseClass)

    def test_set_pose_zero_leaves_identity_matrix(self):
        from app.schemas.pose import Pose
        sensor = self._make_sensor()
        sensor.set_pose(Pose.zero())
        np.testing.assert_array_almost_equal(sensor.transformation, np.eye(4))

    def test_set_pose_x_translation(self):
        from app.schemas.pose import Pose
        sensor = self._make_sensor()
        sensor.set_pose(Pose(x=500.0))
        # Translation should be 500 along x-axis
        assert sensor.transformation[0, 3] == pytest.approx(500.0)
        assert sensor.transformation[1, 3] == pytest.approx(0.0)
        assert sensor.transformation[2, 3] == pytest.approx(0.0)


class TestLidarSensorGetPoseParams:
    """B-16: get_pose_params() returns Pose instance."""

    def _make_sensor(self):
        from unittest.mock import MagicMock
        from app.modules.lidar.node import LidarSensor
        manager = MagicMock()
        return LidarSensor(manager=manager, sensor_id="test-sensor", launch_args="")

    def test_get_pose_params_returns_pose_instance(self):
        from app.schemas.pose import Pose
        sensor = self._make_sensor()
        sensor.set_pose(Pose(x=100.0, yaw=45.0))

        result = sensor.get_pose_params()
        assert isinstance(result, Pose)

    def test_get_pose_params_default_is_zero_pose(self):
        from app.schemas.pose import Pose
        sensor = self._make_sensor()
        result = sensor.get_pose_params()
        assert result == Pose.zero()

    def test_get_pose_params_reflects_set_pose(self):
        from app.schemas.pose import Pose
        sensor = self._make_sensor()
        expected = Pose(x=1.0, y=2.0, z=3.0, roll=10.0, pitch=20.0, yaw=30.0)
        sensor.set_pose(expected)
        assert sensor.get_pose_params() == expected
