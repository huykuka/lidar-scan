"""
Unit tests for sensor_model module - LidarSensor class.
"""
import numpy as np
import pytest

from app.modules.lidar.sensor import LidarSensor


class TestLidarSensorInitialization:
    """Tests for LidarSensor initialization"""
    
    def test_basic_initialization(self):
        """Test basic sensor initialization"""
        sensor = LidarSensor(
            sensor_id="lidar1",
            launch_args="--arg1 --arg2"
        )
        
        assert sensor.id == "lidar1"
        assert sensor.launch_args == "--arg1 --arg2"
        assert sensor.name == "lidar1"  # Defaults to sensor_id
        assert sensor.topic_prefix == "lidar1"  # Defaults to name
        assert sensor.mode == "real"
        assert sensor.pipeline is None
        assert sensor.pipeline_name is None
        assert sensor.pcd_path is None
    
    def test_initialization_with_name(self):
        """Test initialization with custom name"""
        sensor = LidarSensor(
            sensor_id="lidar1",
            name="Front Sensor",
            launch_args="--args"
        )
        
        assert sensor.id == "lidar1"
        assert sensor.name == "Front Sensor"
        assert sensor.topic_prefix == "Front Sensor"  # Defaults to name
    
    def test_initialization_with_topic_prefix(self):
        """Test initialization with custom topic prefix"""
        sensor = LidarSensor(
            sensor_id="lidar1",
            name="Front Sensor",
            topic_prefix="front_lidar",
            launch_args="--args"
        )
        
        assert sensor.topic_prefix == "front_lidar"
    
    def test_initialization_sim_mode(self):
        """Test initialization in simulation mode"""
        sensor = LidarSensor(
            sensor_id="sim1",
            launch_args="",
            mode="sim",
            pcd_path="/path/to/file.pcd"
        )
        
        assert sensor.mode == "sim"
        assert sensor.pcd_path == "/path/to/file.pcd"
    
    def test_transformation_defaults_to_identity(self):
        """Test that transformation defaults to identity matrix"""
        sensor = LidarSensor(
            sensor_id="lidar1",
            launch_args="--args"
        )
        
        expected = np.eye(4)
        np.testing.assert_array_equal(sensor.transformation, expected)
    
    def test_initialization_with_custom_transformation(self):
        """Test initialization with custom transformation matrix"""
        custom_T = np.array([
            [1, 0, 0, 10],
            [0, 1, 0, 20],
            [0, 0, 1, 30],
            [0, 0, 0, 1]
        ])
        
        sensor = LidarSensor(
            sensor_id="lidar1",
            launch_args="--args",
            transformation=custom_T
        )
        
        np.testing.assert_array_equal(sensor.transformation, custom_T)
    
    def test_pose_params_defaults_to_zero(self):
        """Test that pose parameters default to zero"""
        sensor = LidarSensor(
            sensor_id="lidar1",
            launch_args="--args"
        )
        
        expected = {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        assert sensor.pose_params == expected
    
    def test_pipeline_configuration(self):
        """Test initialization with pipeline configuration"""
        from unittest.mock import Mock
        
        mock_pipeline = Mock()
        
        sensor = LidarSensor(
            sensor_id="lidar1",
            launch_args="--args",
            pipeline=mock_pipeline,
            pipeline_name="voxel_downsample"
        )
        
        assert sensor.pipeline is mock_pipeline
        assert sensor.pipeline_name == "voxel_downsample"


class TestSetPose:
    """Tests for set_pose method"""
    
    def test_set_pose_translation_only(self):
        """Test setting pose with translation only"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        result = sensor.set_pose(1.0, 2.0, 3.0)
        
        # Check return value for method chaining
        assert result is sensor
        
        # Check pose params
        assert sensor.pose_params["x"] == 1.0
        assert sensor.pose_params["y"] == 2.0
        assert sensor.pose_params["z"] == 3.0
        assert sensor.pose_params["roll"] == 0.0
        assert sensor.pose_params["pitch"] == 0.0
        assert sensor.pose_params["yaw"] == 0.0
        
        # Check transformation matrix
        assert sensor.transformation[0, 3] == 1.0
        assert sensor.transformation[1, 3] == 2.0
        assert sensor.transformation[2, 3] == 3.0
    
    def test_set_pose_with_rotation(self):
        """Test setting pose with translation and rotation"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        sensor.set_pose(1.0, 2.0, 3.0, roll=10.0, pitch=20.0, yaw=30.0)
        
        # Check pose params
        assert sensor.pose_params["x"] == 1.0
        assert sensor.pose_params["y"] == 2.0
        assert sensor.pose_params["z"] == 3.0
        assert sensor.pose_params["roll"] == 10.0
        assert sensor.pose_params["pitch"] == 20.0
        assert sensor.pose_params["yaw"] == 30.0
        
        # Check that transformation is not identity
        assert not np.array_equal(sensor.transformation, np.eye(4))
    
    def test_set_pose_updates_transformation(self):
        """Test that set_pose updates the transformation matrix"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        
        # Store initial transformation
        initial_T = sensor.transformation.copy()
        
        # Update pose
        sensor.set_pose(5.0, 10.0, 15.0)
        
        # Transformation should have changed
        assert not np.array_equal(sensor.transformation, initial_T)
    
    def test_set_pose_90deg_yaw(self):
        """Test set_pose with 90 degree yaw rotation"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        sensor.set_pose(0, 0, 0, yaw=90)
        
        # Test rotation by transforming a vector
        x_vec = np.array([1, 0, 0, 1])  # Homogeneous
        result = sensor.transformation @ x_vec
        
        # Should rotate X to Y
        np.testing.assert_array_almost_equal(result[:3], [0, 1, 0], decimal=10)
    
    def test_set_pose_method_chaining(self):
        """Test that set_pose returns self for method chaining"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        result = sensor.set_pose(1, 2, 3).set_pose(4, 5, 6)
        
        assert result is sensor
        assert sensor.pose_params["x"] == 4.0  # Last values applied
    
    def test_set_pose_overwrites_previous(self):
        """Test that set_pose overwrites previous pose"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        
        sensor.set_pose(1, 2, 3, roll=10, pitch=20, yaw=30)
        sensor.set_pose(10, 20, 30, roll=45, pitch=60, yaw=90)
        
        assert sensor.pose_params["x"] == 10.0
        assert sensor.pose_params["y"] == 20.0
        assert sensor.pose_params["z"] == 30.0
        assert sensor.pose_params["roll"] == 45.0
        assert sensor.pose_params["pitch"] == 60.0
        assert sensor.pose_params["yaw"] == 90.0
    
    def test_set_pose_negative_values(self):
        """Test set_pose with negative values"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        sensor.set_pose(-1.5, -2.5, -3.5, roll=-10, pitch=-20, yaw=-30)
        
        assert sensor.pose_params["x"] == -1.5
        assert sensor.pose_params["y"] == -2.5
        assert sensor.pose_params["z"] == -3.5
        assert sensor.pose_params["roll"] == -10.0
        assert sensor.pose_params["pitch"] == -20.0
        assert sensor.pose_params["yaw"] == -30.0
    
    def test_set_pose_large_values(self):
        """Test set_pose with large values"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        sensor.set_pose(1000.0, 2000.0, 3000.0, yaw=360)
        
        assert sensor.pose_params["x"] == 1000.0
        assert sensor.pose_params["y"] == 2000.0
        assert sensor.pose_params["z"] == 3000.0
        assert sensor.pose_params["yaw"] == 360.0


class TestGetPoseParams:
    """Tests for get_pose_params method"""
    
    def test_get_pose_params_default(self):
        """Test getting default pose parameters"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        params = sensor.get_pose_params()
        
        expected = {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        assert params == expected
    
    def test_get_pose_params_after_set(self):
        """Test getting pose parameters after setting them"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        sensor.set_pose(1.0, 2.0, 3.0, roll=10.0, pitch=20.0, yaw=30.0)
        
        params = sensor.get_pose_params()
        
        assert params["x"] == 1.0
        assert params["y"] == 2.0
        assert params["z"] == 3.0
        assert params["roll"] == 10.0
        assert params["pitch"] == 20.0
        assert params["yaw"] == 30.0
    
    def test_get_pose_params_returns_copy(self):
        """Test that get_pose_params returns a copy, not reference"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        sensor.set_pose(1.0, 2.0, 3.0)
        
        params = sensor.get_pose_params()
        params["x"] = 999.0  # Modify returned dict
        
        # Original should not be affected
        assert sensor.pose_params["x"] == 1.0
    
    def test_get_pose_params_all_keys(self):
        """Test that all expected keys are present"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        params = sensor.get_pose_params()
        
        expected_keys = {"x", "y", "z", "roll", "pitch", "yaw"}
        assert set(params.keys()) == expected_keys
    
    def test_get_pose_params_float_types(self):
        """Test that all values are floats"""
        sensor = LidarSensor(sensor_id="lidar1", launch_args="--args")
        sensor.set_pose(1, 2, 3, roll=10, pitch=20, yaw=30)  # Use ints
        
        params = sensor.get_pose_params()
        
        for value in params.values():
            assert isinstance(value, float)


class TestLidarSensorIntegration:
    """Integration tests for LidarSensor class"""
    
    def test_typical_usage_real_mode(self):
        """Test typical usage pattern for real hardware mode"""
        sensor = LidarSensor(
            sensor_id="front_lidar",
            name="Front Lidar",
            topic_prefix="front",
            launch_args="--ip 192.168.1.100",
            pipeline_name="default",
            mode="real"
        )
        sensor.set_pose(1.5, 0.0, 0.5, roll=0, pitch=0, yaw=0)
        
        assert sensor.id == "front_lidar"
        assert sensor.name == "Front Lidar"
        assert sensor.topic_prefix == "front"
        assert sensor.mode == "real"
        assert sensor.pose_params["x"] == 1.5
    
    def test_typical_usage_sim_mode(self):
        """Test typical usage pattern for simulation mode"""
        sensor = LidarSensor(
            sensor_id="sim_lidar",
            name="Simulated Lidar",
            launch_args="",
            mode="sim",
            pcd_path="/data/sample.pcd"
        )
        sensor.set_pose(0, 0, 2.0, yaw=90)
        
        assert sensor.mode == "sim"
        assert sensor.pcd_path == "/data/sample.pcd"
        assert sensor.pose_params["z"] == 2.0
        assert sensor.pose_params["yaw"] == 90.0
    
    def test_sensor_with_pipeline_and_pose(self):
        """Test sensor with both pipeline and pose configuration"""
        from unittest.mock import Mock
        
        mock_pipeline = Mock()
        
        sensor = LidarSensor(
            sensor_id="complex_sensor",
            launch_args="--args",
            pipeline=mock_pipeline,
            pipeline_name="custom_pipeline"
        )
        sensor.set_pose(2.0, 3.0, 1.0, roll=5, pitch=10, yaw=15)
        
        assert sensor.pipeline is mock_pipeline
        assert sensor.pipeline_name == "custom_pipeline"
        
        params = sensor.get_pose_params()
        assert params["x"] == 2.0
        assert params["roll"] == 5.0
