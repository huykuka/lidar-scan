"""
B-19 (also covers B-05): Integration test for DB migration backfill.

Tests cover:
- Node with flat pose keys in config_json gets migrated to config["pose"]
- After migration, flat keys are removed from config
- Migration is idempotent (running twice produces same result)
- Node that already has config["pose"] is not re-migrated
"""
import json
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db.models import Base, NodeModel


@pytest.fixture()
def memory_engine():
    """In-memory SQLite engine with fresh schema for isolation."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return engine


def _insert_node_with_flat_pose(conn, node_id: str, flat_config: dict):
    """Insert a node row with flat pose keys at the top level of config."""
    conn.execute(
        text(
            "INSERT INTO nodes (id, name, type, category, enabled, visible, config, x, y) "
            "VALUES (:id, :name, :type, :category, 1, 1, :config, 100, 100)"
        ),
        {
            "id": node_id,
            "name": "Test Sensor",
            "type": "sensor",
            "category": "sensor",
            "config": json.dumps(flat_config),
        }
    )


class TestPoseBackfillMigration:
    """B-19: Data-only backfill migration tests."""

    def test_flat_pose_keys_migrated_to_nested_pose(self, memory_engine):
        from app.db.migrate import ensure_schema

        # Insert node with flat pose keys
        with memory_engine.begin() as conn:
            _insert_node_with_flat_pose(conn, "sensor-001", {
                "lidar_type": "multiscan",
                "hostname": "192.168.1.10",
                "x": 100.0,
                "y": 0.0,
                "z": 50.0,
                "roll": 0.0,
                "pitch": 0.0,
                "yaw": 45.0,
            })

        ensure_schema(memory_engine)

        with memory_engine.connect() as conn:
            row = conn.execute(text("SELECT config FROM nodes WHERE id = 'sensor-001'")).fetchone()
            cfg = json.loads(row[0])

        assert "pose" in cfg
        assert cfg["pose"]["x"] == 100.0
        assert cfg["pose"]["y"] == 0.0
        assert cfg["pose"]["z"] == 50.0
        assert cfg["pose"]["roll"] == 0.0
        assert cfg["pose"]["pitch"] == 0.0
        assert cfg["pose"]["yaw"] == 45.0

    def test_flat_keys_removed_after_migration(self, memory_engine):
        from app.db.migrate import ensure_schema

        with memory_engine.begin() as conn:
            _insert_node_with_flat_pose(conn, "sensor-002", {
                "lidar_type": "multiscan",
                "x": 100.0,
                "y": 20.0,
                "z": 30.0,
                "roll": 5.0,
                "pitch": -5.0,
                "yaw": 90.0,
            })

        ensure_schema(memory_engine)

        with memory_engine.connect() as conn:
            row = conn.execute(text("SELECT config FROM nodes WHERE id = 'sensor-002'")).fetchone()
            cfg = json.loads(row[0])

        # Flat pose keys must be gone
        for key in ("x", "y", "z", "roll", "pitch", "yaw"):
            assert key not in cfg, f"Flat key '{key}' still present after migration"

    def test_non_pose_config_keys_preserved(self, memory_engine):
        from app.db.migrate import ensure_schema

        with memory_engine.begin() as conn:
            _insert_node_with_flat_pose(conn, "sensor-003", {
                "lidar_type": "multiscan",
                "hostname": "192.168.1.10",
                "mode": "real",
                "x": 10.0,
                "y": 0.0,
                "z": 0.0,
                "roll": 0.0,
                "pitch": 0.0,
                "yaw": 0.0,
            })

        ensure_schema(memory_engine)

        with memory_engine.connect() as conn:
            row = conn.execute(text("SELECT config FROM nodes WHERE id = 'sensor-003'")).fetchone()
            cfg = json.loads(row[0])

        assert cfg["lidar_type"] == "multiscan"
        assert cfg["hostname"] == "192.168.1.10"
        assert cfg["mode"] == "real"

    def test_migration_is_idempotent(self, memory_engine):
        from app.db.migrate import ensure_schema

        with memory_engine.begin() as conn:
            _insert_node_with_flat_pose(conn, "sensor-004", {
                "lidar_type": "multiscan",
                "x": 100.0,
                "y": 0.0,
                "z": 50.0,
                "roll": 0.0,
                "pitch": 0.0,
                "yaw": 45.0,
            })

        # Run migration twice
        ensure_schema(memory_engine)
        ensure_schema(memory_engine)

        with memory_engine.connect() as conn:
            row = conn.execute(text("SELECT config FROM nodes WHERE id = 'sensor-004'")).fetchone()
            cfg = json.loads(row[0])

        assert cfg["pose"]["x"] == 100.0
        assert cfg["pose"]["yaw"] == 45.0
        # Flat keys should still be absent
        for key in ("x", "y", "z", "roll", "pitch", "yaw"):
            assert key not in cfg

    def test_node_with_existing_pose_key_not_overwritten(self, memory_engine):
        from app.db.migrate import ensure_schema

        existing_pose = {"x": 999.0, "y": 999.0, "z": 999.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        config_with_pose = {
            "lidar_type": "multiscan",
            "pose": existing_pose,
        }

        with memory_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO nodes (id, name, type, category, enabled, visible, config, x, y) "
                    "VALUES ('sensor-005', 'Sensor', 'sensor', 'sensor', 1, 1, :config, 100, 100)"
                ),
                {"config": json.dumps(config_with_pose)}
            )

        ensure_schema(memory_engine)

        with memory_engine.connect() as conn:
            row = conn.execute(text("SELECT config FROM nodes WHERE id = 'sensor-005'")).fetchone()
            cfg = json.loads(row[0])

        # Must not be overwritten
        assert cfg["pose"]["x"] == 999.0

    def test_node_without_any_pose_keys_untouched(self, memory_engine):
        from app.db.migrate import ensure_schema

        config_no_pose = {
            "fusion_method": "icp_registration",
            "distance_threshold": 0.05,
        }

        with memory_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO nodes (id, name, type, category, enabled, visible, config, x, y) "
                    "VALUES ('fusion-001', 'Fusion', 'fusion', 'fusion', 1, 1, :config, 100, 100)"
                ),
                {"config": json.dumps(config_no_pose)}
            )

        ensure_schema(memory_engine)

        with memory_engine.connect() as conn:
            row = conn.execute(text("SELECT config FROM nodes WHERE id = 'fusion-001'")).fetchone()
            cfg = json.loads(row[0])

        # No pose key should be added for non-sensor nodes without flat keys
        assert "pose" not in cfg
        assert cfg["fusion_method"] == "icp_registration"
