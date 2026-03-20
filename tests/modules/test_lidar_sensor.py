"""Tests for LidarSensor class"""
import pytest
import time
from unittest.mock import Mock, MagicMock
from app.modules.lidar.sensor import LidarSensor
from app.schemas.status import NodeStatusUpdate, OperationalState, ApplicationState



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


class TestLidarSensorEmitStatus:
    """Test LidarSensor.emit_status() standardized status reporting"""
    
    def test_emit_status_stopped(self):
        """Worker not started → STOPPED with disconnected status"""
        mock_manager = Mock()
        mock_manager.node_runtime_status = {}
        
        sensor = LidarSensor(
            manager=mock_manager,
            sensor_id="sensor-001",
            launch_args="test",
            mode="real",
            name="Test Sensor"
        )
        
        status = sensor.emit_status()
        
        assert isinstance(status, NodeStatusUpdate)
        assert status.node_id == "sensor-001"
        assert status.operational_state == OperationalState.STOPPED
        assert status.application_state is not None
        assert status.application_state.label == "connection_status"
        assert status.application_state.value == "disconnected"
        assert status.application_state.color == "red"
        assert status.error_message is None
    
    def test_emit_status_initialize(self):
        """Worker spawned → INITIALIZE with starting status"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-002",
            launch_args="test",
            mode="real"
        )
        
        # Simulate runtime status showing process starting
        runtime_status = {
            "sensor-002": {
                "process_alive": True,
                "connection_status": "starting",
                "last_error": None,
            }
        }
        sensor.manager.node_runtime_status = runtime_status
        
        # Mock alive process
        sensor._process = MagicMock()
        sensor._process.is_alive.return_value = True
        
        status = sensor.emit_status()
        
        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.INITIALIZE
        assert status.application_state.label == "connection_status"
        assert status.application_state.value == "starting"
        assert status.application_state.color == "orange"
    
    def test_emit_status_running(self):
        """Receiving frames → RUNNING with connected status"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-003",
            launch_args="test",
            mode="real"
        )
        
        # Simulate runtime status showing active connection
        runtime_status = {
            "sensor-003": {
                "process_alive": True,
                "connection_status": "connected",
                "last_frame_at": time.time(),
                "last_error": None,
            }
        }
        sensor.manager.node_runtime_status = runtime_status
        
        # Mock alive process
        sensor._process = MagicMock()
        sensor._process.is_alive.return_value = True
        
        status = sensor.emit_status()
        
        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state.label == "connection_status"
        assert status.application_state.value == "connected"
        assert status.application_state.color == "green"
    
    def test_emit_status_error(self):
        """UDP timeout → ERROR with disconnected status and error message"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-004",
            launch_args="test",
            mode="real"
        )
        
        # Simulate runtime status showing error
        runtime_status = {
            "sensor-004": {
                "process_alive": True,
                "connection_status": "disconnected",
                "last_error": "UDP socket timeout after 5s",
            }
        }
        sensor.manager.node_runtime_status = runtime_status
        
        # Mock alive process (still running but errored)
        sensor._process = MagicMock()
        sensor._process.is_alive.return_value = True
        
        status = sensor.emit_status()
        
        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.ERROR
        assert status.application_state.label == "connection_status"
        assert status.application_state.value == "disconnected"
        assert status.application_state.color == "red"
        assert status.error_message == "UDP socket timeout after 5s"
    
    def test_emit_status_worker_stopped(self):
        """Worker process stopped → STOPPED with disconnected status"""
        sensor = LidarSensor(
            manager=Mock(),
            sensor_id="sensor-005",
            launch_args="test",
            mode="real"
        )
        
        # Simulate runtime status after stop
        runtime_status = {
            "sensor-005": {
                "process_alive": False,
                "connection_status": "disconnected",
                "last_error": None,
            }
        }
        sensor.manager.node_runtime_status = runtime_status
        
        # Mock dead process
        sensor._process = MagicMock()
        sensor._process.is_alive.return_value = False
        
        status = sensor.emit_status()
        
        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.STOPPED
        assert status.application_state.value == "disconnected"
        assert status.application_state.color == "red"

