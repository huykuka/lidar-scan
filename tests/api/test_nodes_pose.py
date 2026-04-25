"""
B-18: Integration tests for nodes API with Pose object.

Node creation is now exclusively via PUT /api/v1/dag/config (atomic).
Tests cover:
- PUT /dag/config with sensor node + pose → round-trip GET /nodes/{id} returns same pose
- PUT /dag/config with sensor node, pose accessible at top-level not inside config
- PUT /dag/config with pose.yaw = 270 → 422 (angle out of range, validated by NodeRecord/Pose)
- PUT /dag/config with pose.yaw = 180 → 200 (boundary passes)
- PUT /dag/config with pose.yaw = -180 → 200 (negative boundary passes)
- GET /nodes → all sensor nodes have pose field; non-sensor nodes have pose: null
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _put_dag(client, base_version: int, nodes: list, edges: list | None = None):
    """Perform PUT /api/v1/dag/config with mocked reload."""
    body = {"base_version": base_version, "nodes": nodes, "edges": edges or []}
    with patch(
        "app.api.v1.dag.service.node_manager.reload_config",
        new_callable=AsyncMock,
    ):
        return client.put("/api/v1/dag/config", json=body)


SENSOR_NODE = {
    "id": "sensor_pose_01",
    "name": "Test Front LiDAR",
    "type": "sensor",
    "category": "sensor",
    "enabled": True,
    "visible": True,
    "config": {
        "lidar_type": "multiscan",
        "hostname": "192.168.1.10",

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

FUSION_NODE = {
    "id": "fusion_01",
    "name": "Test Fusion",
    "type": "fusion",
    "category": "fusion",
    "enabled": True,
    "visible": True,
    "config": {
        "fusion_method": "icp_registration",
    },
    "pose": None,
    "x": 300.0,
    "y": 200.0,
}


class TestNodesPoseRoundTrip:
    """B-18: PUT /dag/config → GET /nodes/{id} round-trip with pose object."""

    def test_create_sensor_with_pose_returns_200(self, client):
        resp = _put_dag(client, 0, [SENSOR_NODE])
        assert resp.status_code == 200

    def test_create_sensor_pose_round_trip(self, client):
        """PUT with pose → GET /nodes/{id} returns same pose at top level."""
        put_resp = _put_dag(client, 0, [SENSOR_NODE])
        assert put_resp.status_code == 200

        get_resp = client.get("/api/v1/nodes/sensor_pose_01")
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
        _put_dag(client, 0, [SENSOR_NODE])

        get_resp = client.get("/api/v1/nodes/sensor_pose_01")
        node = get_resp.json()

        # pose must NOT appear inside config
        assert "x" not in node.get("config", {})
        assert "roll" not in node.get("config", {})
        assert "pose" not in node.get("config", {})


class TestNodesPoseValidation:
    """B-18: Pose field validation (angle bounds) via NodeRecord schema in PUT /dag/config."""

    def _node_with_pose(self, pose: Dict[str, Any]) -> Dict[str, Any]:
        return {**SENSOR_NODE, "id": "v_sensor_01", "pose": pose}

    def test_yaw_270_rejected_422(self, client):
        node = self._node_with_pose(
            {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 270.0}
        )
        body = {"base_version": 0, "nodes": [node], "edges": []}
        resp = client.put("/api/v1/dag/config", json=body)
        assert resp.status_code == 422

    def test_yaw_180_passes_200(self, client):
        node = self._node_with_pose(
            {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 180.0}
        )
        resp = _put_dag(client, 0, [node])
        assert resp.status_code == 200

    def test_yaw_neg180_passes_200(self, client):
        node = self._node_with_pose(
            {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": -180.0}
        )
        resp = _put_dag(client, 0, [node])
        assert resp.status_code == 200

    def test_roll_exceeds_180_rejected_422(self, client):
        node = self._node_with_pose(
            {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 190.0, "pitch": 0.0, "yaw": 0.0}
        )
        body = {"base_version": 0, "nodes": [node], "edges": []}
        resp = client.put("/api/v1/dag/config", json=body)
        assert resp.status_code == 422


class TestNodesListPoseField:
    """B-18: GET /nodes returns pose for sensor nodes, null for others."""

    def test_get_nodes_list_sensor_has_pose(self, client):
        _put_dag(client, 0, [SENSOR_NODE])

        resp = client.get("/api/v1/nodes")
        assert resp.status_code == 200
        nodes = resp.json()

        sensor_nodes = [n for n in nodes if n["type"] == "sensor"]
        assert len(sensor_nodes) > 0
        for node in sensor_nodes:
            assert "pose" in node
            assert node["pose"] is not None

    def test_get_nodes_list_fusion_has_null_pose(self, client):
        _put_dag(client, 0, [FUSION_NODE])

        resp = client.get("/api/v1/nodes")
        assert resp.status_code == 200
        nodes = resp.json()

        fusion_nodes = [n for n in nodes if n["type"] == "fusion"]
        assert len(fusion_nodes) > 0
        for node in fusion_nodes:
            assert "pose" in node
            assert node["pose"] is None

    def test_create_sensor_without_pose_defaults_to_zero(self, client):
        """Sensor created without pose (pose: null) gets null or zero pose via GET."""
        no_pose_node = {
            "id": "noposenode01",
            "name": "No-Pose Sensor",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {"lidar_type": "multiscan", "hostname": "192.168.1.10"},
            "pose": None,
            "x": 0.0,
            "y": 0.0,
        }
        _put_dag(client, 0, [no_pose_node])

        get_resp = client.get("/api/v1/nodes/noposenode01")
        node = get_resp.json()

        # Sensor with null pose: pose may be None or a zero pose object
        assert "pose" in node
        if node["pose"] is not None:
            pose = node["pose"]
            assert pose["x"] == 0.0
            assert pose["yaw"] == 0.0
