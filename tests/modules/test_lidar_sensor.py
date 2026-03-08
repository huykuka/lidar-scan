"""Tests for LidarSensor class"""
import pytest
from unittest.mock import Mock, MagicMock
from app.modules.lidar.sensor import LidarSensor


class TestLidarSensorStatus:
    """Test LidarSensor.get_status() method"""
    
    def test_get_status_includes_lidar_type(self):
        """Status includes lidar_type field"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-001",
            launch_args="./launch/sick_tim_5xx.launch hostname:=192.168.0.1",
            mode="real",
            name="Test Sensor"
        )
        sensor.lidar_type = "tim_5xx"
        sensor.lidar_display_name = "SICK TiM5xx Family"
        
        status = sensor.get_status({})
        
        assert status["lidar_type"] == "tim_5xx"
        assert status["lidar_display_name"] == "SICK TiM5xx Family"
    
    def test_get_status_with_multiscan_type(self):
        """Status correctly reports multiScan type"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-002",
            launch_args="./launch/sick_multiscan.launch hostname:=192.168.0.50",
            mode="real",
            name="Front Scanner"
        )
        sensor.lidar_type = "multiscan"
        sensor.lidar_display_name = "SICK multiScan100"
        
        status = sensor.get_status({})
        
        assert status["lidar_type"] == "multiscan"
        assert status["lidar_display_name"] == "SICK multiScan100"
    
    def test_get_status_standard_fields_present(self):
        """Status includes all standard fields"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-003",
            launch_args="./launch/sick_lms_1xx.launch hostname:=192.168.0.1",
            mode="real",
            name="Test LiDAR"
        )
        sensor.lidar_type = "lms_1xx"
        sensor.lidar_display_name = "SICK LMS1xx"
        
        status = sensor.get_status({})
        
        assert "id" in status
        assert "name" in status
        assert "type" in status
        assert "mode" in status
        assert "topic" in status
        assert "running" in status
        assert "connection_status" in status
        assert "last_frame_at" in status
        assert "frame_age_seconds" in status
        assert "last_error" in status
    
    def test_get_status_without_lidar_type_optional(self):
        """Status works when lidar_type not set (backward compat)"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-004",
            launch_args="./launch/sick_multiscan.launch",
            mode="real"
        )
        # Don't set lidar_type
        
        status = sensor.get_status({})
        
        # Fields should be absent or None, not crash
        assert "id" in status
        assert "name" in status


class TestLidarSensorAttributes:
    """Test LidarSensor attributes and initialization"""
    
    def test_sensor_has_lidar_type_attribute(self):
        """LidarSensor can store lidar_type"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-001",
            launch_args="test",
            mode="real"
        )
        sensor.lidar_type = "tim_7xx"
        assert sensor.lidar_type == "tim_7xx"
    
    def test_sensor_has_lidar_display_name_attribute(self):
        """LidarSensor can store lidar_display_name"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-002",
            launch_args="test",
            mode="real"
        )
        sensor.lidar_display_name = "SICK TiM7xx Family (Non-Safety)"
        assert sensor.lidar_display_name == "SICK TiM7xx Family (Non-Safety)"
    
    def test_sensor_mode_persists(self):
        """LidarSensor preserves mode through initialization"""
        sensor_real = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-real",
            launch_args="test",
            mode="real"
        )
        assert sensor_real.mode == "real"
        
        sensor_sim = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-sim",
            launch_args="test",
            mode="sim",
            pcd_path="/path/to/test.pcd"
        )
        assert sensor_sim.mode == "sim"


class TestLidarSensorIntegration:
    """Test LidarSensor integration with profiles"""
    
    def test_sensor_launch_args_valid_format(self):
        """Sensor accepts properly formatted launch_args"""
        launch_args = "./launch/sick_tim_5xx.launch hostname:=192.168.0.1 port:=2112 add_transform_xyz_rpy:=0,0,0,0,0,0"
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-001",
            launch_args=launch_args,
            mode="real"
        )
        assert sensor.launch_args == launch_args
    
    def test_sensor_with_multicast_launch_args(self):
        """Sensor accepts multiScan launch args with UDP parameters"""
        launch_args = "./launch/sick_multiscan.launch hostname:=192.168.0.50 udp_port:=2115 udp_receiver_ip:=192.168.0.10 imu_udp_port:=7503 add_transform_xyz_rpy:=0,0,0,0,0,0"
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-002",
            launch_args=launch_args,
            mode="real"
        )
        sensor.lidar_type = "multiscan"
        assert sensor.lidar_type == "multiscan"
        assert "udp_port:=" in sensor.launch_args
    
    def test_sensor_with_tcp_device_no_port_args(self):
        """Sensor accepts launch args without port for TCP devices"""
        launch_args = "./launch/sick_lms_1xx.launch hostname:=192.168.0.50 add_transform_xyz_rpy:=0,0,0,0,0,0"
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-003",
            launch_args=launch_args,
            mode="real"
        )
        sensor.lidar_type = "lms_1xx"
        assert "hostname:=" in sensor.launch_args
        assert "port:=" not in sensor.launch_args


class TestLidarSensorStatusRuntimeTracking:
    """Test status tracking with runtime_status dict"""
    
    def test_get_status_with_runtime_data(self):
        """Status includes runtime tracking data"""
        import time
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-001",
            launch_args="test",
            mode="real"
        )
        sensor.lidar_type = "tim_5xx"
        sensor.lidar_display_name = "SICK TiM5xx Family"
        
        current_time = time.time()
        runtime_status = {
            "sensor-001": {
                "last_frame_at": current_time,
                "last_error": None,
                "connection_status": "connected"
            }
        }
        
        status = sensor.get_status(runtime_status)
        
        assert status["connection_status"] == "connected"
        assert status["last_error"] is None
        assert status["last_frame_at"] == current_time
    
    def test_get_status_with_error_state(self):
        """Status reports error states"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-002",
            launch_args="test",
            mode="real"
        )
        
        runtime_status = {
            "sensor-002": {
                "last_frame_at": None,
                "last_error": "Connection timeout",
                "connection_status": "disconnected"
            }
        }
        
        status = sensor.get_status(runtime_status)
        
        assert status["connection_status"] == "disconnected"
        assert status["last_error"] == "Connection timeout"


class TestLidarSensorEdgeCases:
    """Test edge cases for sensor behavior"""
    
    def test_sensor_without_manager_initializes(self):
        """Sensor can initialize with mock manager"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="test-id",
            launch_args="test-args",
            mode="real"
        )
        assert sensor.id == "test-id"
    
    def test_sensor_name_defaults_to_id(self):
        """Sensor name defaults to ID if not provided"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-abc-123",
            launch_args="test",
            mode="real"
        )
        assert sensor.name == "sensor-abc-123"
    
    def test_sensor_custom_name_overrides_id(self):
        """Custom name is used when provided"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-001",
            launch_args="test",
            mode="real",
            name="Front Scanner"
        )
        assert sensor.name == "Front Scanner"
    
    def test_sensor_with_zero_pose(self):
        """Sensor correctly handles zero pose"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-001",
            launch_args="test",
            mode="real"
        )
        sensor.set_pose(0, 0, 0, 0, 0, 0)
        pose = sensor.get_pose_params()
        
        assert pose["x"] == 0.0
        assert pose["y"] == 0.0
        assert pose["z"] == 0.0
        assert pose["roll"] == 0.0
        assert pose["pitch"] == 0.0
        assert pose["yaw"] == 0.0
    
    def test_sensor_with_nonzero_pose(self):
        """Sensor correctly stores non-zero pose"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-002",
            launch_args="test",
            mode="real"
        )
        sensor.set_pose(1.5, 2.5, 0.3, 0.1, 0.2, 1.57)
        pose = sensor.get_pose_params()
        
        assert pose["x"] == 1.5
        assert pose["y"] == 2.5
        assert pose["z"] == 0.3
        assert pose["roll"] == 0.1
        assert pose["pitch"] == 0.2
        assert pose["yaw"] == 1.57
