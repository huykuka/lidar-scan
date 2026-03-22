"""
TDD Tests for calibration-page-redesign backend changes.

Group 1: Database Migration
- Task 1.1: New columns in migrate.py
- Task 1.2: New Mapped columns in models.py
"""
import json
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db.models import Base, CalibrationHistoryModel
from app.db.migrate import ensure_schema
from app.db.session import init_engine


class TestMigrationNewColumns:
    """Task 1.1 — ensure_schema() adds 5 new columns idempotently."""

    def test_all_five_new_columns_added(self, tmp_path, monkeypatch):
        """ensure_schema() adds node_id, accepted_at, accepted_by, rollback_source_id, registration_method_json."""
        db_file = tmp_path / "test.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
        engine = init_engine()
        ensure_schema(engine)

        with engine.connect() as conn:
            rows = conn.exec_driver_sql("PRAGMA table_info(calibration_history)").fetchall()
            col_names = {r[1] for r in rows}

        assert "node_id" in col_names
        assert "accepted_at" in col_names
        assert "accepted_by" in col_names
        assert "rollback_source_id" in col_names
        assert "registration_method_json" in col_names

    def test_ensure_schema_idempotent(self, tmp_path, monkeypatch):
        """Running ensure_schema() twice does not raise errors."""
        db_file = tmp_path / "test.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
        engine = init_engine()
        ensure_schema(engine)
        # Run a second time — must not raise
        ensure_schema(engine)

    def test_registration_method_json_default_is_null(self, tmp_path, monkeypatch):
        """registration_method_json defaults to 'null' when not explicitly provided."""
        db_file = tmp_path / "test.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
        engine = init_engine()
        ensure_schema(engine)

        # Insert a record without explicitly setting registration_method_json
        with Session(engine) as db:
            record = CalibrationHistoryModel(
                id=uuid.uuid4().hex,
                sensor_id="sensor-1",
                reference_sensor_id="ref-1",
                timestamp="2026-01-01T00:00:00Z",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used_json='["icp"]',
                pose_before_json='{"x":0,"y":0,"z":0,"roll":0,"pitch":0,"yaw":0}',
                pose_after_json='{"x":1,"y":0,"z":0,"roll":0,"pitch":0,"yaw":0}',
                transformation_matrix_json="[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]",
                accepted=False,
                notes="",
                source_sensor_id="sensor-1",
                processing_chain_json="[]",
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            # to_dict() must not raise and registration_method must parse as None
            d = record.to_dict()
            assert d["registration_method"] is None


class TestModelNewColumns:
    """Task 1.2 — CalibrationHistoryModel includes all 5 new fields in to_dict()."""

    def test_to_dict_includes_node_id(self, tmp_path, monkeypatch):
        """to_dict() includes node_id key."""
        db_file = tmp_path / "test.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
        engine = init_engine()
        ensure_schema(engine)

        with Session(engine) as db:
            record = CalibrationHistoryModel(
                id=uuid.uuid4().hex,
                sensor_id="sensor-1",
                reference_sensor_id="ref-1",
                timestamp="2026-01-01T00:00:00Z",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used_json='["icp"]',
                pose_before_json='{"x":0,"y":0,"z":0,"roll":0,"pitch":0,"yaw":0}',
                pose_after_json='{"x":1,"y":0,"z":0,"roll":0,"pitch":0,"yaw":0}',
                transformation_matrix_json="[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]",
                accepted=False,
                notes="",
                source_sensor_id="sensor-1",
                processing_chain_json="[]",
                run_id="run-123",
                node_id="cal-node-1",
                accepted_at=None,
                accepted_by=None,
                rollback_source_id=None,
                registration_method_json="null",
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            d = record.to_dict()
            assert "node_id" in d
            assert "accepted_at" in d
            assert "accepted_by" in d
            assert "rollback_source_id" in d
            assert "registration_method" in d

    def test_to_dict_registration_method_parsed_from_json(self, tmp_path, monkeypatch):
        """to_dict() parses registration_method_json into a Python object."""
        db_file = tmp_path / "test.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
        engine = init_engine()
        ensure_schema(engine)

        method = {"method": "icp", "stages": ["global", "icp"]}
        with Session(engine) as db:
            record = CalibrationHistoryModel(
                id=uuid.uuid4().hex,
                sensor_id="sensor-1",
                reference_sensor_id="ref-1",
                timestamp="2026-01-01T00:00:00Z",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used_json='["icp"]',
                pose_before_json='{"x":0,"y":0,"z":0,"roll":0,"pitch":0,"yaw":0}',
                pose_after_json='{"x":1,"y":0,"z":0,"roll":0,"pitch":0,"yaw":0}',
                transformation_matrix_json="[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]",
                accepted=False,
                notes="",
                source_sensor_id="sensor-1",
                processing_chain_json="[]",
                run_id="run-123",
                registration_method_json=json.dumps(method),
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            d = record.to_dict()
            assert d["registration_method"] == method

    def test_to_dict_no_error_with_null_fields(self, tmp_path, monkeypatch):
        """CalibrationHistoryModel().to_dict() does not raise with all nullable fields null."""
        db_file = tmp_path / "test.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
        engine = init_engine()
        ensure_schema(engine)

        with Session(engine) as db:
            record = CalibrationHistoryModel(
                id=uuid.uuid4().hex,
                sensor_id="sensor-1",
                reference_sensor_id="ref-1",
                timestamp="2026-01-01T00:00:00Z",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used_json='["icp"]',
                pose_before_json='{"x":0,"y":0,"z":0,"roll":0,"pitch":0,"yaw":0}',
                pose_after_json='{"x":1,"y":0,"z":0,"roll":0,"pitch":0,"yaw":0}',
                transformation_matrix_json="[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]",
                accepted=False,
                notes="",
                source_sensor_id="sensor-1",
                processing_chain_json="[]",
                run_id=None,
                # New optional fields left as None / default
                node_id=None,
                accepted_at=None,
                accepted_by=None,
                rollback_source_id=None,
                registration_method_json="null",
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            d = record.to_dict()
            assert d["node_id"] is None
            assert d["accepted_at"] is None
            assert d["accepted_by"] is None
            assert d["rollback_source_id"] is None
            assert d["registration_method"] is None
