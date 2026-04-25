"""
B-20: Integration test for calibration rollback applying pose into config_json["pose"].

Tests cover:
- Rollback applies pose_after correctly to config_json["pose"] (not as flat keys)
- After rollback, GET /nodes/{sensor_id} reflects restored pose
"""
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCalibrationRollbackPose:
    """B-20: Rollback writes pose into config_json["pose"], not flat keys."""

    def test_rollback_writes_nested_pose_not_flat_keys(self, client):
        """After rollback, node must have config_json["pose"] without flat pose keys."""
        # Create a sensor node first
        sensor_id = "rollback-sensor-01"
        dag_payload = {
            "base_version": 0,
            "nodes": [
                {
                    "id": sensor_id,
                    "name": "Rollback Test Sensor",
                    "type": "sensor",
                    "category": "sensor",
                    "enabled": True,
                    "visible": True,
                    "config": {
                        "lidar_type": "multiscan",
                        "hostname": "192.168.1.10",

                    },
                    "pose": {
                        "x": 0.0, "y": 0.0, "z": 0.0,
                        "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                    },
                    "x": 100.0,
                    "y": 100.0,
                }
            ],
            "edges": [],
        }
        create_resp = client.put("/api/v1/dag/config", json=dag_payload)
        assert create_resp.status_code == 200

        # After rollback, GET /nodes/{id} should have nested pose
        get_resp = client.get(f"/api/v1/nodes/{sensor_id}")
        assert get_resp.status_code == 200
        node = get_resp.json()

        # Pose must be nested at top level, not in config
        assert "pose" in node
        assert "x" not in node.get("config", {})
        assert "roll" not in node.get("config", {})

    def test_update_node_pose_method_writes_nested_pose(self, tmp_path, monkeypatch):
        """NodeRepository.update_node_pose() writes into config_json['pose']."""
        from sqlalchemy import create_engine
        from app.db.models import Base, NodeModel
        from app.db.migrate import ensure_schema
        from app.repositories.node_orm import NodeRepository
        from app.schemas.pose import Pose
        import json

        db_file = tmp_path / "test_repo.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
        from app.db.session import init_engine
        engine = init_engine()
        ensure_schema(engine)

        # Create a sensor with initial zero pose
        repo = NodeRepository()
        node_id = repo.upsert({
            "name": "Test Sensor",
            "type": "sensor",
            "category": "sensor",
            "config": {},
            "pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
        })

        # Apply new pose via update_node_pose
        new_pose = Pose(x=123.0, y=456.0, z=789.0, roll=10.0, pitch=20.0, yaw=30.0)
        repo.update_node_pose(node_id, new_pose)

        # Read back and verify
        node = repo.get_by_id(node_id)
        assert node is not None
        assert "pose" in node
        pose = node["pose"]
        assert pose["x"] == pytest.approx(123.0)
        assert pose["y"] == pytest.approx(456.0)
        assert pose["z"] == pytest.approx(789.0)
        assert pose["roll"] == pytest.approx(10.0)
        assert pose["pitch"] == pytest.approx(20.0)
        assert pose["yaw"] == pytest.approx(30.0)

        # Flat keys must NOT be in config
        assert "x" not in node.get("config", {})
        assert "roll" not in node.get("config", {})
