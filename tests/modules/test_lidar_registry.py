"""Tests for sensor node registry and schema"""
import pytest
from app.services.nodes.schema import NodeDefinition, PropertySchema
from app.modules.lidar.registry import build_sensor
from app.modules.lidar.profiles import get_all_profiles


class TestRegistrySchema:
    """Test node definition schema for sensor node"""
    
    def test_sensor_definition_has_lidar_type_property(self):
        """First property should be lidar_type dropdown"""
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        assert sensor_def is not None
        assert len(sensor_def.properties) > 0
        first_prop = sensor_def.properties[0]
        assert first_prop.name == "lidar_type"
        assert first_prop.type == "select"
    
    def test_lidar_type_property_has_25_options(self):
        """lidar_type select should have 25 options (all profiles)"""
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        lidar_type_prop = next(p for p in sensor_def.properties if p.name == "lidar_type")
        assert len(lidar_type_prop.options) == 25
    
    def test_lidar_type_options_match_profiles(self):
        """Dropdown options should match profile model_ids"""
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        lidar_type_prop = next(p for p in sensor_def.properties if p.name == "lidar_type")
        
        profiles = get_all_profiles()
        profile_ids = {p.model_id for p in profiles}
        option_values = {opt["value"] for opt in lidar_type_prop.options}
        
        assert option_values == profile_ids
    
    def test_lidar_type_default_is_multiscan(self):
        """Default should be multiscan for backward compatibility"""
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        lidar_type_prop = next(p for p in sensor_def.properties if p.name == "lidar_type")
        assert lidar_type_prop.default == "multiscan"
    
    def test_hostname_has_mode_depends_on(self):
        """hostname should only show when mode == 'real'"""
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        hostname_prop = next(p for p in sensor_def.properties if p.name == "hostname")
        assert hostname_prop.depends_on is not None
        assert "mode" in hostname_prop.depends_on
        assert "real" in hostname_prop.depends_on["mode"]
    
    def test_port_has_lidar_type_and_mode_depends_on(self):
        """port should depend on both mode and lidar_type"""
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        port_prop = next(p for p in sensor_def.properties if p.name == "port")
        assert port_prop.depends_on is not None
        assert "mode" in port_prop.depends_on
        assert "lidar_type" in port_prop.depends_on
        assert "real" in port_prop.depends_on["mode"]
        # Port should be visible for these models
        assert "multiscan" in port_prop.depends_on["lidar_type"]
        assert "tim_5xx" in port_prop.depends_on["lidar_type"]
    
    def test_port_not_for_tcp_devices(self):
        """port field should NOT be visible for TCP-only devices"""
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        port_prop = next(p for p in sensor_def.properties if p.name == "port")
        
        # LMS and MRS devices should NOT be in the depends_on list
        tcp_only = ["lms_1xx", "lms_5xx", "lms_4xxx", "lms_4000", "mrs_1xxx", "mrs_6xxx"]
        for model_id in tcp_only:
            assert model_id not in port_prop.depends_on["lidar_type"], \
                f"{model_id} should not have port field"
    
    def test_udp_receiver_ip_depends_on_picoscan_and_multiscan(self):
        """udp_receiver_ip should show for multiScan and picoScan devices"""
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        udp_ip_prop = next(p for p in sensor_def.properties if p.name == "udp_receiver_ip")
        assert udp_ip_prop.depends_on is not None
        assert "lidar_type" in udp_ip_prop.depends_on
        # Should have multiscan at minimum
        assert "multiscan" in udp_ip_prop.depends_on["lidar_type"]
    
    def test_imu_udp_port_depends_on_multiscan(self):
        """imu_udp_port should only show for multiScan"""
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        imu_prop = next(p for p in sensor_def.properties if p.name == "imu_udp_port")
        assert imu_prop.depends_on is not None
        assert "lidar_type" in imu_prop.depends_on
        assert imu_prop.depends_on["lidar_type"] == ["multiscan"]
    
    def test_pcd_path_depends_on_sim_mode(self):
        """pcd_path should only show when mode == 'sim'"""
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        pcd_prop = next(p for p in sensor_def.properties if p.name == "pcd_path")
        assert pcd_prop.depends_on is not None
        assert "mode" in pcd_prop.depends_on
        assert pcd_prop.depends_on["mode"] == ["sim"]
    
    def test_no_udp_port_property_exists(self):
        """Old udp_port property should be renamed to 'port'"""
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        prop_names = {p.name for p in sensor_def.properties}
        assert "udp_port" not in prop_names
        assert "port" in prop_names
    
    def test_property_schema_depends_on_field(self):
        """PropertySchema must support depends_on field"""
        # Create a property with depends_on
        prop = PropertySchema(
            name="test_field",
            label="Test",
            type="string",
            depends_on={"mode": ["real"], "lidar_type": ["multiscan"]}
        )
        assert prop.depends_on is not None
        assert prop.depends_on["mode"] == ["real"]
        assert prop.depends_on["lidar_type"] == ["multiscan"]
    
    def test_property_schema_depends_on_none_by_default(self):
        """PropertySchema.depends_on defaults to None"""
        prop = PropertySchema(
            name="always_visible",
            label="Always Visible",
            type="string"
        )
        assert prop.depends_on is None


class TestConditionalPropertyLogic:
    """Test the logic of conditional field visibility"""
    
    def test_mode_real_shows_hostname(self):
        """Mode=real reveals hostname"""
        form_values = {"mode": "real"}
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        hostname_prop = next(p for p in sensor_def.properties if p.name == "hostname")
        
        # Simulate depends_on check
        visible = self._check_depends_on(hostname_prop.depends_on, form_values)
        assert visible is True
    
    def test_mode_sim_hides_hostname(self):
        """Mode=sim hides hostname"""
        form_values = {"mode": "sim"}
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        hostname_prop = next(p for p in sensor_def.properties if p.name == "hostname")
        
        visible = self._check_depends_on(hostname_prop.depends_on, form_values)
        assert visible is False
    
    def test_multiscan_shows_udp_receiver_ip(self):
        """lidar_type=multiscan reveals udp_receiver_ip"""
        form_values = {"mode": "real", "lidar_type": "multiscan"}
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        udp_ip_prop = next(p for p in sensor_def.properties if p.name == "udp_receiver_ip")
        
        visible = self._check_depends_on(udp_ip_prop.depends_on, form_values)
        assert visible is True
    
    def test_tim_5xx_hides_udp_receiver_ip(self):
        """lidar_type=tim_5xx hides udp_receiver_ip"""
        form_values = {"mode": "real", "lidar_type": "tim_5xx"}
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        udp_ip_prop = next(p for p in sensor_def.properties if p.name == "udp_receiver_ip")
        
        visible = self._check_depends_on(udp_ip_prop.depends_on, form_values)
        assert visible is False
    
    def test_multiscan_shows_imu_port(self):
        """lidar_type=multiscan reveals imu_udp_port"""
        form_values = {"mode": "real", "lidar_type": "multiscan"}
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        imu_prop = next(p for p in sensor_def.properties if p.name == "imu_udp_port")
        
        visible = self._check_depends_on(imu_prop.depends_on, form_values)
        assert visible is True
    
    def test_lms_1xx_hides_port(self):
        """lidar_type=lms_1xx hides port (TCP only)"""
        form_values = {"mode": "real", "lidar_type": "lms_1xx"}
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        port_prop = next(p for p in sensor_def.properties if p.name == "port")
        
        visible = self._check_depends_on(port_prop.depends_on, form_values)
        assert visible is False
    
    def test_tim_7xx_shows_port(self):
        """lidar_type=tim_7xx shows port"""
        form_values = {"mode": "real", "lidar_type": "tim_7xx"}
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        port_prop = next(p for p in sensor_def.properties if p.name == "port")
        
        visible = self._check_depends_on(port_prop.depends_on, form_values)
        assert visible is True
    
    def test_sim_mode_shows_pcd_path(self):
        """Mode=sim reveals pcd_path"""
        form_values = {"mode": "sim"}
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        pcd_prop = next(p for p in sensor_def.properties if p.name == "pcd_path")
        
        visible = self._check_depends_on(pcd_prop.depends_on, form_values)
        assert visible is True
    
    def test_real_mode_hides_pcd_path(self):
        """Mode=real hides pcd_path"""
        form_values = {"mode": "real"}
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        pcd_prop = next(p for p in sensor_def.properties if p.name == "pcd_path")
        
        visible = self._check_depends_on(pcd_prop.depends_on, form_values)
        assert visible is False
    
    def test_all_tcp_devices_hide_port(self):
        """All TCP-only devices hide port field"""
        tcp_devices = ["lms_1xx", "lms_5xx", "lms_4xxx", "lms_4000", "mrs_1xxx", "mrs_6xxx"]
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        port_prop = next(p for p in sensor_def.properties if p.name == "port")
        
        for device in tcp_devices:
            form_values = {"mode": "real", "lidar_type": device}
            visible = self._check_depends_on(port_prop.depends_on, form_values)
            assert visible is False, f"{device} should not show port field"
    
    def test_all_port_capable_devices_show_port(self):
        """All port-capable devices show port field"""
        port_devices = ["multiscan", "tim_240", "tim_5xx", "tim_7xx", "tim_7xxs"]
        from app.services.nodes.schema import node_schema_registry
        sensor_def = node_schema_registry.get("sensor")
        port_prop = next(p for p in sensor_def.properties if p.name == "port")
        
        for device in port_devices:
            form_values = {"mode": "real", "lidar_type": device}
            visible = self._check_depends_on(port_prop.depends_on, form_values)
            assert visible is True, f"{device} should show port field"
    
    @staticmethod
    def _check_depends_on(depends_on, form_values):
        """Simulate Angular depends_on logic"""
        if depends_on is None:
            return True
        return all(
            form_values.get(key) in allowed_values
            for key, allowed_values in depends_on.items()
        )


class TestBuildSensorIntegration:
    """Test build_sensor function with profiles"""
    
    def test_build_sensor_with_multiscan_config(self, mock_service_context):
        """build_sensor correctly processes multiScan config"""
        node = {
            "id": "sensor-001",
            "name": "Front LiDAR",
            "config": {
                "lidar_type": "multiscan",
                "mode": "real",
                "hostname": "192.168.0.50",
                "port": 2115,
                "udp_receiver_ip": "192.168.0.10",
                "imu_udp_port": 7503,
                "throttle_ms": 0,
                "x": 0.0, "y": 0.0, "z": 0.5,
                "roll": 0.0, "pitch": 0.0, "yaw": 0.0
            }
        }
        
        sensor = build_sensor(node, mock_service_context, [])
        
        assert sensor.id == "sensor-001"
        assert sensor.name == "Front LiDAR"
        assert sensor.mode == "real"
        assert "sick_multiscan.launch" in sensor.launch_args
        assert "udp_port:=2115" in sensor.launch_args
        assert "udp_receiver_ip:=192.168.0.10" in sensor.launch_args
    
    def test_build_sensor_with_tim_7xx_config(self, mock_service_context):
        """build_sensor correctly processes TiM7xx config"""
        node = {
            "id": "sensor-002",
            "name": "Side LiDAR",
            "config": {
                "lidar_type": "tim_7xx",
                "mode": "real",
                "hostname": "192.168.0.100",
                "port": 2112,
                "throttle_ms": 50,
                "x": 0.5, "y": -0.5, "z": 0.3,
                "roll": 0.0, "pitch": 0.0, "yaw": 1.57
            }
        }
        
        sensor = build_sensor(node, mock_service_context, [])
        
        assert sensor.id == "sensor-002"
        assert sensor.mode == "real"
        assert "sick_tim_7xx.launch" in sensor.launch_args
        assert "port:=2112" in sensor.launch_args
        assert "udp_port" not in sensor.launch_args
    
    def test_build_sensor_with_lms_1xx_config(self, mock_service_context):
        """build_sensor correctly processes LMS1xx config (no port arg)"""
        node = {
            "id": "sensor-003",
            "name": "Back LiDAR",
            "config": {
                "lidar_type": "lms_1xx",
                "mode": "real",
                "hostname": "192.168.0.200",
                "throttle_ms": 0,
                "x": -1.0, "y": 0.0, "z": 0.2,
                "roll": 0.0, "pitch": 0.0, "yaw": 3.14
            }
        }
        
        sensor = build_sensor(node, mock_service_context, [])
        
        assert "sick_lms_1xx.launch" in sensor.launch_args
        assert "port:=" not in sensor.launch_args
        assert "udp_port:=" not in sensor.launch_args
        assert "hostname:=192.168.0.200" in sensor.launch_args
    
    def test_build_sensor_default_lidar_type_is_multiscan(self, mock_service_context):
        """Backward compatibility: no lidar_type defaults to multiScan"""
        node = {
            "id": "sensor-004",
            "name": "Legacy Sensor",
            "config": {
                "mode": "real",
                "hostname": "192.168.0.50",
                # No lidar_type specified
                "x": 0, "y": 0, "z": 0,
                "roll": 0, "pitch": 0, "yaw": 0
            }
        }
        
        sensor = build_sensor(node, mock_service_context, [])
        
        # Should default to multiScan launch args
        assert "sick_multiscan.launch" in sensor.launch_args
    
    def test_build_sensor_with_pose_transform(self, mock_service_context):
        """Pose parameters are correctly formatted - Note: pose handling in registry"""
        node = {
            "id": "sensor-005",
            "name": "Positioned LiDAR",
            "config": {
                "lidar_type": "tim_5xx",
                "mode": "real",
                "hostname": "192.168.0.1",
                "port": 2112,
                "throttle_ms": 0,
            },
            "pose": {"x": 1.5, "y": 2.5, "z": 0.3, "roll": 0.1, "pitch": 0.2, "yaw": 1.57}
        }
        
        sensor = build_sensor(node, mock_service_context, [])
        
        # The sensor is created with the pose - it's used internally for transformation
        # but not necessarily in the launch_args (which are only device connection params)
        assert sensor.get_pose_params().x == 1.5


@pytest.fixture
def mock_service_context():
    """Fixture for mock service context"""
    class MockTopicRegistry:
        def register(self, desired_prefix, node_id):
            return desired_prefix
    
    class MockServiceContext:
        def __init__(self):
            self._topic_registry = MockTopicRegistry()
    
    return MockServiceContext()
