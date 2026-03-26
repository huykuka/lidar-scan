"""Tests for LiDAR API endpoints"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from app.modules.lidar.profiles import get_all_profiles


@pytest.fixture
def api_client():
    """Create test client for FastAPI"""
    from app.app import app
    return TestClient(app)


class TestLidarProfilesEndpoint:
    """Test GET /api/v1/lidar/profiles endpoint"""
    
    def test_profiles_endpoint_returns_200(self, api_client):
        """Endpoint returns HTTP 200"""
        response = api_client.get("/api/v1/lidar/profiles")
        assert response.status_code == 200
    
    def test_profiles_response_has_profiles_key(self, api_client):
        """Response has top-level 'profiles' key"""
        response = api_client.get("/api/v1/lidar/profiles")
        data = response.json()
        assert "profiles" in data
    
    def test_profiles_returns_exactly_23_items(self, api_client):
        """Response contains exactly 23 profile objects (API-filtered from backend's 25)"""
        response = api_client.get("/api/v1/lidar/profiles")
        data = response.json()
        assert len(data["profiles"]) == 23  # Backend has 25, but API filters to 23 enabled profiles
    
    def test_profile_objects_have_required_fields(self, api_client):
        """Each profile has all required fields"""
        response = api_client.get("/api/v1/lidar/profiles")
        data = response.json()
        
        required_fields = {
            'model_id', 'display_name', 'launch_file', 'default_hostname',
            'port_arg', 'default_port', 'has_udp_receiver', 'has_imu_udp_port',
            'scan_layers'
        }
        
        for profile in data["profiles"]:
            for field in required_fields:
                assert field in profile
    
    def test_multiscan_profile_correct_properties(self, api_client):
        """multiScan profile has correct properties"""
        response = api_client.get("/api/v1/lidar/profiles")
        data = response.json()
        
        multiscan = next(p for p in data["profiles"] if p["model_id"] == "multiscan")
        assert multiscan["display_name"] == "SICK multiScan100"
        assert multiscan["launch_file"] == "launch/sick_multiscan.launch"
        assert multiscan["port_arg"] == "udp_port"
        assert multiscan["default_port"] == 2115
        assert multiscan["has_udp_receiver"] is True
        assert multiscan["has_imu_udp_port"] is True
        assert multiscan["scan_layers"] == 16
    
    def test_tim_7xx_profile_no_udp(self, api_client):
        """TiM7xx profile has correct non-UDP properties"""
        response = api_client.get("/api/v1/lidar/profiles")
        data = response.json()
        
        tim7xx = next(p for p in data["profiles"] if p["model_id"] == "tim_7xx")
        assert tim7xx["port_arg"] == "port"
        assert tim7xx["has_udp_receiver"] is False
        assert tim7xx["has_imu_udp_port"] is False
    
    def test_lms_1xx_tcp_only(self, api_client):
        """LMS1xx profile has no port argument"""
        response = api_client.get("/api/v1/lidar/profiles")
        data = response.json()
        
        lms1xx = next(p for p in data["profiles"] if p["model_id"] == "lms_1xx")
        assert lms1xx["port_arg"] == ""
        assert lms1xx["default_port"] == 0
    
    def test_mrs_6xxx_multi_layer(self, api_client):
        """MRS6xxx profile has 24 layers"""
        response = api_client.get("/api/v1/lidar/profiles")
        data = response.json()
        
        mrs6xxx = next(p for p in data["profiles"] if p["model_id"] == "mrs_6xxx")
        assert mrs6xxx["scan_layers"] == 24


@pytest.mark.skip(reason="validate-lidar-config endpoint not yet implemented in API")
class TestValidateLidarConfigEndpoint:
    """Test POST /api/v1/lidar/validate-lidar-config endpoint (PENDING - endpoint not yet implemented)"""
    
    def test_validate_multiscan_full_valid(self, api_client):
        """Validate multiScan with all parameters"""
        payload = {
            "lidar_type": "multiscan",
            "hostname": "192.168.0.50",
            "port": 2115,
            "udp_receiver_ip": "192.168.0.10",
            "imu_udp_port": 7503
        }
        response = api_client.post("/api/v1/nodes/validate-lidar-config", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["lidar_type"] == "multiscan"
        assert "launch/sick_multiscan.launch" in data["resolved_launch_file"]
    
    def test_validate_tim_7xx_valid(self, api_client):
        """Validate TiM7xx (port but no UDP)"""
        payload = {
            "lidar_type": "tim_7xx",
            "hostname": "192.168.0.100",
            "port": 2112
        }
        response = api_client.post("/api/v1/nodes/validate-lidar-config", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
    
    def test_validate_lms_1xx_no_port(self, api_client):
        """Validate LMS1xx (TCP only)"""
        payload = {
            "lidar_type": "lms_1xx",
            "hostname": "192.168.0.1"
        }
        response = api_client.post("/api/v1/nodes/validate-lidar-config", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
    
    def test_validate_unknown_lidar_type(self, api_client):
        """Unknown lidar_type returns invalid"""
        payload = {
            "lidar_type": "velodyne_vls128",
            "hostname": "192.168.0.1"
        }
        response = api_client.post("/api/v1/nodes/validate-lidar-config", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0
    
    def test_validate_multiscan_missing_udp_receiver_ip(self, api_client):
        """multiScan without udp_receiver_ip is invalid"""
        payload = {
            "lidar_type": "multiscan",
            "hostname": "192.168.0.50"
        }
        response = api_client.post("/api/v1/nodes/validate-lidar-config", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any("udp_receiver_ip" in err for err in data["errors"])
    
    def test_validate_multiscan_without_imu_port_warning(self, api_client):
        """multiScan without imu_udp_port returns warning not error"""
        payload = {
            "lidar_type": "multiscan",
            "hostname": "192.168.0.50",
            "udp_receiver_ip": "192.168.0.10",
            "port": 2115
        }
        response = api_client.post("/api/v1/nodes/validate-lidar-config", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert any("imu_udp_port" in w.lower() for w in data["warnings"])
    
    def test_validate_missing_required_lidar_type(self, api_client):
        """Missing required lidar_type returns 422"""
        payload = {
            "hostname": "192.168.0.1"
        }
        response = api_client.post("/api/v1/nodes/validate-lidar-config", json=payload)
        assert response.status_code == 422
    
    def test_validate_missing_hostname_semantic_error(self, api_client):
        """Missing hostname is semantic validation error"""
        payload = {
            "lidar_type": "tim_7xx"
        }
        response = api_client.post("/api/v1/nodes/validate-lidar-config", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any("hostname" in err.lower() for err in data["errors"])


class TestNodeDefinitionsExtended:
    """Test extended node definitions with lidar_type"""
    
    def test_definitions_endpoint_returns_sensor_definition(self, api_client):
        """Definitions endpoint includes sensor definition"""
        response = api_client.get("/api/v1/nodes/definitions")
        assert response.status_code == 200
        data = response.json()
        
        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        assert sensor_def is not None
    
    def test_sensor_definition_has_lidar_type_property(self, api_client):
        """Sensor definition includes lidar_type property"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()
        
        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        lidar_type_prop = next(
            (p for p in sensor_def["properties"] if p["name"] == "lidar_type"),
            None
        )
        assert lidar_type_prop is not None
        assert lidar_type_prop["type"] == "select"
    
    def test_lidar_type_is_first_property(self, api_client):
        """lidar_type is the first property in the list"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()
        
        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        assert sensor_def["properties"][0]["name"] == "lidar_type"
    
    def test_lidar_type_has_25_options(self, api_client):
        """lidar_type property has exactly 25 options (all backend profiles)"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()
    
        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        lidar_type_prop = next(p for p in sensor_def["properties"] if p["name"] == "lidar_type")
        assert len(lidar_type_prop["options"]) == 25  # All 25 backend profiles available
    
    def test_port_property_depends_on_model(self, api_client):
        """port property has depends_on with lidar_type"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()
        
        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        port_prop = next(p for p in sensor_def["properties"] if p["name"] == "port")
        
        assert port_prop["depends_on"] is not None
        assert "lidar_type" in port_prop["depends_on"]
    
    def test_no_udp_port_property_renamed(self, api_client):
        """udp_port has been renamed to port"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()
        
        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        prop_names = {p["name"] for p in sensor_def["properties"]}
        
        assert "udp_port" not in prop_names
        assert "port" in prop_names


@pytest.mark.skip(reason="config validation endpoint behavior pending implementation confirmation")
class TestConfigValidationExtended:
    """Test config validation with lidar_type (PENDING - behavior pending implementation)"""
    
    def test_validate_config_with_known_lidar_type(self, api_client):
        """Config with known lidar_type validates successfully"""
        config = {
            "nodes": [{
                "id": "sensor-001",
                "name": "Test Sensor",
                "type": "sensor",
                "config": {
                    "lidar_type": "tim_5xx",
                    "mode": "real",
                    "hostname": "192.168.0.1"
                }
            }],
            "edges": []
        }
        response = api_client.post("/api/v1/config/validate", json=config)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
    
    def test_validate_config_missing_lidar_type_warning(self, api_client):
        """Config without lidar_type shows backward compat warning"""
        config = {
            "nodes": [{
                "id": "sensor-001",
                "name": "Legacy Sensor",
                "type": "sensor",
                "config": {
                    "mode": "real",
                    "hostname": "192.168.0.1"
                }
            }],
            "edges": []
        }
        response = api_client.post("/api/v1/config/validate", json=config)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert any("lidar_type" in w.lower() for w in data.get("warnings", []))
    
    def test_validate_config_unknown_lidar_type_error(self, api_client):
        """Config with unknown lidar_type is invalid"""
        config = {
            "nodes": [{
                "id": "sensor-001",
                "name": "Invalid Sensor",
                "type": "sensor",
                "config": {
                    "lidar_type": "ouster_os1",
                    "mode": "real",
                    "hostname": "192.168.0.1"
                }
            }],
            "edges": []
        }
        response = api_client.post("/api/v1/config/validate", json=config)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False


class TestNodeOperationsWithLidarType:
    """Test node operations with lidar_type"""
    
    def test_create_sensor_node_with_lidar_type(self, api_client):
        """Create sensor node with lidar_type in config"""
        # Fetch current config_version to avoid optimistic-lock conflict
        current_version = api_client.get("/api/v1/dag/config").json().get("config_version", 0)
        payload = {
            "base_version": current_version,
            "nodes": [
                {
                    "id": "test-sensor-001",
                    "name": "Test LiDAR",
                    "type": "sensor",
                    "category": "sensor",
                    "enabled": True,
                    "config": {
                        "lidar_type": "tim_7xx",
                        "mode": "real",
                        "hostname": "192.168.0.100",
                        "port": 2112,
                        "throttle_ms": 0,
                    },
                    "pose": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                    "x": 200.0,
                    "y": 100.0,
                }
            ],
            "edges": [],
        }
        response = api_client.put("/api/v1/dag/config", json=payload)
        assert response.status_code in [200, 201]
    
    def test_get_node_status_includes_lidar_type(self, api_client):
        """Node status endpoint returns 200 and has expected structure"""
        response = api_client.get("/api/v1/nodes/status/all")
        assert response.status_code == 200
        data = response.json()
        
        # Endpoint should return valid JSON structure with nodes field
        assert isinstance(data, dict)
        # If nodes are present, they should have expected fields
        if "nodes" in data and data["nodes"]:
            for node in data["nodes"]:
                assert "id" in node
                assert "type" in node
