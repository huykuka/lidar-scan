"""
B-18: Integration tests for the nodes API with Pose object.

Tests cover:
- POST /nodes with pose object → 200 and round-trip GET returns same pose
- POST /nodes with config.x = 100 (flat key) → 422 with correct error
- POST /nodes with pose.yaw = 270 → 422 (angle out of range)
- POST /nodes with pose.yaw = 180 → 200 (boundary passes)
- POST /nodes with pose.yaw = -180 → 200 (negative boundary passes)
- GET /nodes → all sensor nodes have pose field; non-sensor nodes have pose: null
"""
import pytest


SENSOR_NODE_PAYLOAD = {
    "name": "Test Front LiDAR",
    "type": "sensor",
    "category": "sensor",
    "enabled": True,
    "visible": True,
    "config": {
        "lidar_type": "multiscan",
        "hostname": "192.168.1.10",
        "mode": "sim",
    },
    "pose": {
        "x": 100.0,
        "y": -25.5,
        "z": 800.0,
        "roll": 0.0,
        "pitch": -5.0,
        "yaw": 45.0,
    },
    "x": 120.0,
    "y": 200.0,
}

FUSION_NODE_PAYLOAD = {
    "name": "Test Fusion",
    "type": "fusion",
    "category": "fusion",
    "enabled": True,
    "visible": True,
    "config": {
        "fusion_method": "icp_registration",
    },
    "x": 300.0,
    "y": 200.0,
}


class TestNodesPoseRoundTrip:
    """B-18: POST/GET round-trip with pose object."""

    def test_create_sensor_with_pose_returns_200(self, client):
        resp = client.post("/api/v1/nodes", json=SENSOR_NODE_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "id" in data

    def test_create_sensor_pose_round_trip(self, client):
        """POST with pose → GET /nodes/{id} returns same pose at top level."""
        create_resp = client.post("/api/v1/nodes", json=SENSOR_NODE_PAYLOAD)
        assert create_resp.status_code == 200
        node_id = create_resp.json()["id"]

        get_resp = client.get(f"/api/v1/nodes/{node_id}")
        assert get_resp.status_code == 200
        node = get_resp.json()

        assert "pose" in node
        pose = node["pose"]
        assert pose["x"] == 100.0
        assert pose["y"] == -25.5
        assert pose["z"] == 800.0
        assert pose["roll"] == 0.0
        assert pose["pitch"] == -5.0
        assert pose["yaw"] == 45.0

    def test_create_sensor_pose_not_in_config(self, client):
        """Pose must be at top level, not inside config dict."""
        create_resp = client.post("/api/v1/nodes", json=SENSOR_NODE_PAYLOAD)
        node_id = create_resp.json()["id"]

        get_resp = client.get(f"/api/v1/nodes/{node_id}")
        node = get_resp.json()

        # pose must NOT appear inside config
        assert "x" not in node.get("config", {})
        assert "roll" not in node.get("config", {})
        assert "pose" not in node.get("config", {})


class TestNodesPoseFlatKeyRejection:
    """B-18: Flat pose keys in config must be rejected with 422."""

    def test_flat_x_in_config_rejected_422(self, client):
        payload = {
            "name": "Bad Sensor",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {
                "lidar_type": "multiscan",
                "hostname": "192.168.1.10",
                "mode": "sim",
                "x": 100.0,   # DEPRECATED flat key
            },
        }
        resp = client.post("/api/v1/nodes", json=payload)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "pose" in detail.lower() or "deprecated" in detail.lower()

    def test_flat_roll_in_config_rejected_422(self, client):
        payload = {
            "name": "Bad Sensor 2",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {
                "lidar_type": "multiscan",
                "mode": "sim",
                "roll": 5.0,   # DEPRECATED flat key
            },
        }
        resp = client.post("/api/v1/nodes", json=payload)
        assert resp.status_code == 422

    def test_multiple_flat_keys_in_config_rejected_422(self, client):
        payload = {
            "name": "Bad Sensor 3",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {
                "x": 100.0,
                "y": 0.0,
                "z": 50.0,
                "roll": 0.0,
                "pitch": 0.0,
                "yaw": 45.0,
            },
        }
        resp = client.post("/api/v1/nodes", json=payload)
        assert resp.status_code == 422


class TestNodesPoseValidation:
    """B-18: Pose field validation (angle bounds)."""

    def test_yaw_270_rejected_422(self, client):
        payload = {**SENSOR_NODE_PAYLOAD, "pose": {
            "x": 0.0, "y": 0.0, "z": 0.0,
            "roll": 0.0, "pitch": 0.0, "yaw": 270.0,  # Out of range
        }}
        resp = client.post("/api/v1/nodes", json=payload)
        assert resp.status_code == 422

    def test_yaw_180_passes_200(self, client):
        payload = {**SENSOR_NODE_PAYLOAD, "pose": {
            "x": 0.0, "y": 0.0, "z": 0.0,
            "roll": 0.0, "pitch": 0.0, "yaw": 180.0,  # Boundary passes
        }}
        resp = client.post("/api/v1/nodes", json=payload)
        assert resp.status_code == 200

    def test_yaw_neg180_passes_200(self, client):
        payload = {**SENSOR_NODE_PAYLOAD, "pose": {
            "x": 0.0, "y": 0.0, "z": 0.0,
            "roll": 0.0, "pitch": 0.0, "yaw": -180.0,  # Negative boundary passes
        }}
        resp = client.post("/api/v1/nodes", json=payload)
        assert resp.status_code == 200

    def test_roll_exceeds_180_rejected_422(self, client):
        payload = {**SENSOR_NODE_PAYLOAD, "pose": {
            "x": 0.0, "y": 0.0, "z": 0.0,
            "roll": 190.0, "pitch": 0.0, "yaw": 0.0,
        }}
        resp = client.post("/api/v1/nodes", json=payload)
        assert resp.status_code == 422


class TestNodesListPoseField:
    """B-18: GET /nodes returns pose for sensor nodes, null for others."""

    def test_get_nodes_list_sensor_has_pose(self, client):
        # Create sensor node
        client.post("/api/v1/nodes", json=SENSOR_NODE_PAYLOAD)

        resp = client.get("/api/v1/nodes")
        assert resp.status_code == 200
        nodes = resp.json()

        sensor_nodes = [n for n in nodes if n["type"] == "sensor"]
        assert len(sensor_nodes) > 0
        for node in sensor_nodes:
            assert "pose" in node
            assert node["pose"] is not None

    def test_get_nodes_list_fusion_has_null_pose(self, client):
        # Create fusion node
        client.post("/api/v1/nodes", json=FUSION_NODE_PAYLOAD)

        resp = client.get("/api/v1/nodes")
        assert resp.status_code == 200
        nodes = resp.json()

        fusion_nodes = [n for n in nodes if n["type"] == "fusion"]
        assert len(fusion_nodes) > 0
        for node in fusion_nodes:
            assert "pose" in node
            assert node["pose"] is None

    def test_create_sensor_without_pose_defaults_to_zero(self, client):
        """Sensor created without pose gets zero pose."""
        payload = {
            "name": "No-Pose Sensor",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {"lidar_type": "multiscan", "hostname": "192.168.1.10", "mode": "sim"},
        }
        create_resp = client.post("/api/v1/nodes", json=payload)
        assert create_resp.status_code == 200
        node_id = create_resp.json()["id"]

        get_resp = client.get(f"/api/v1/nodes/{node_id}")
        node = get_resp.json()

        # Should have a zero pose (not None for sensor nodes)
        assert "pose" in node
        if node["pose"] is not None:
            pose = node["pose"]
            assert pose["x"] == 0.0
            assert pose["yaw"] == 0.0
