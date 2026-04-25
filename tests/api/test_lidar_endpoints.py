"""Tests for LiDAR API endpoints"""
import pytest
from fastapi.testclient import TestClient
from app.modules.lidar.profiles import get_all_profiles, get_enabled_profiles


@pytest.fixture
def api_client():
    """Create test client for FastAPI"""
    from app.app import app
    return TestClient(app)


class TestLidarProfilesRemovedEndpoint:
    """Verify GET /api/v1/lidar/profiles has been removed."""

    def test_profiles_endpoint_returns_404(self, api_client):
        """The /lidar/profiles endpoint no longer exists"""
        response = api_client.get("/api/v1/lidar/profiles")
        assert response.status_code == 404


class TestNodeDefinitionsWithEnrichedProfiles:
    """Test that node definitions carry full profile metadata in lidar_type options."""

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
        assert len(lidar_type_prop["options"]) == 25

    def test_options_contain_full_profile_metadata(self, api_client):
        """Each option carries all profile fields needed by the frontend"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()

        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        lidar_type_prop = next(p for p in sensor_def["properties"] if p["name"] == "lidar_type")

        required_keys = {
            "label", "value", "launch_file", "default_hostname",
            "port_arg", "default_port", "has_udp_receiver", "has_imu_udp_port",
            "scan_layers", "thumbnail_url", "icon_name", "icon_color", "disabled",
        }

        for opt in lidar_type_prop["options"]:
            for key in required_keys:
                assert key in opt, f"Option {opt['value']} missing key '{key}'"

    def test_multiscan_option_correct_properties(self, api_client):
        """multiScan option has correct profile properties"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()

        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        lidar_type_prop = next(p for p in sensor_def["properties"] if p["name"] == "lidar_type")

        multiscan = next(o for o in lidar_type_prop["options"] if o["value"] == "multiscan")
        assert multiscan["label"] == "SICK multiScan100"
        assert multiscan["launch_file"] == "launch/sick_multiscan.launch"
        assert multiscan["port_arg"] == "udp_port"
        assert multiscan["default_port"] == 2115
        assert multiscan["has_udp_receiver"] is True
        assert multiscan["has_imu_udp_port"] is True
        assert multiscan["scan_layers"] == 16
        assert multiscan["disabled"] is False

    def test_tim_7xx_option_no_udp(self, api_client):
        """TiM7xx option has correct non-UDP properties"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()

        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        lidar_type_prop = next(p for p in sensor_def["properties"] if p["name"] == "lidar_type")

        tim7xx = next(o for o in lidar_type_prop["options"] if o["value"] == "tim_7xx")
        assert tim7xx["port_arg"] == "port"
        assert tim7xx["has_udp_receiver"] is False
        assert tim7xx["has_imu_udp_port"] is False

    def test_lms_1xx_tcp_only(self, api_client):
        """LMS1xx option has no port argument"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()

        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        lidar_type_prop = next(p for p in sensor_def["properties"] if p["name"] == "lidar_type")

        lms1xx = next(o for o in lidar_type_prop["options"] if o["value"] == "lms_1xx")
        assert lms1xx["port_arg"] == ""
        assert lms1xx["default_port"] == 0

    def test_mrs_6xxx_multi_layer(self, api_client):
        """MRS6xxx option has 24 layers"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()

        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        lidar_type_prop = next(p for p in sensor_def["properties"] if p["name"] == "lidar_type")

        mrs6xxx = next(o for o in lidar_type_prop["options"] if o["value"] == "mrs_6xxx")
        assert mrs6xxx["scan_layers"] == 24

    def test_options_match_all_profiles(self, api_client):
        """Option values match all profile model_ids"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()

        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        lidar_type_prop = next(p for p in sensor_def["properties"] if p["name"] == "lidar_type")

        profiles = get_all_profiles()
        profile_ids = {p.model_id for p in profiles}
        option_values = {opt["value"] for opt in lidar_type_prop["options"]}

        assert option_values == profile_ids

    def test_enabled_profiles_count_matches(self, api_client):
        """Number of non-disabled options matches enabled profiles"""
        response = api_client.get("/api/v1/nodes/definitions")
        data = response.json()

        sensor_def = next((d for d in data if d["type"] == "sensor"), None)
        lidar_type_prop = next(p for p in sensor_def["properties"] if p["name"] == "lidar_type")

        enabled_options = [o for o in lidar_type_prop["options"] if not o["disabled"]]
        enabled_profiles = get_enabled_profiles()
        assert len(enabled_options) == len(enabled_profiles)

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
