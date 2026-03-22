"""
TDD Tests for calibration-page-redesign backend changes.

Group 2: ORM Functions
- Task 2.1: update create_calibration_record() signature
- Task 2.2: fix and activate update_calibration_acceptance()
- Task 2.3: add get_calibration_history_by_node()
- Task 2.4: add run_id filter to get_calibration_history()
"""
import json
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, CalibrationHistoryModel
from app.db.migrate import ensure_schema
from app.db.session import init_engine
from app.repositories import calibration_orm


def make_engine(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    engine = init_engine()
    ensure_schema(engine)
    return engine


def _make_db_session(engine):
    from sqlalchemy.orm import sessionmaker
    SessionFactory = sessionmaker(bind=engine)
    return SessionFactory()


def _create_test_record(
    db,
    sensor_id="sensor-1",
    reference_sensor_id="ref-1",
    fitness=0.9,
    rmse=0.003,
    quality="excellent",
    node_id=None,
    run_id=None,
    accepted=False,
    accepted_at=None,
    rollback_source_id=None,
    registration_method=None,
):
    return calibration_orm.create_calibration_record(
        db=db,
        record_id=uuid.uuid4().hex,
        sensor_id=sensor_id,
        reference_sensor_id=reference_sensor_id,
        fitness=fitness,
        rmse=rmse,
        quality=quality,
        stages_used=["icp"],
        pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
        pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
        transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
        accepted=accepted,
        notes="",
        source_sensor_id=sensor_id,
        processing_chain=[],
        run_id=run_id,
        node_id=node_id,
        accepted_at=accepted_at,
        rollback_source_id=rollback_source_id,
        registration_method=registration_method,
    )


class TestCreateCalibrationRecordNewParams:
    """Task 2.1 — create_calibration_record() accepts and persists 5 new params."""

    def test_create_with_existing_params_still_works(self, tmp_path, monkeypatch):
        """Existing callers still work with no new params."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            record = calibration_orm.create_calibration_record(
                db=db,
                record_id=uuid.uuid4().hex,
                sensor_id="sensor-1",
                reference_sensor_id="ref-1",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used=["icp"],
                pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            )
            assert record is not None
        finally:
            db.close()

    def test_create_with_node_id_persisted(self, tmp_path, monkeypatch):
        """node_id is stored and can be read back."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            record_id = uuid.uuid4().hex
            calibration_orm.create_calibration_record(
                db=db,
                record_id=record_id,
                sensor_id="sensor-1",
                reference_sensor_id="ref-1",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used=["icp"],
                pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                node_id="cal-node-abc",
            )
            fetched = calibration_orm.get_calibration_by_id(db, record_id)
            assert fetched is not None
            assert fetched.node_id == "cal-node-abc"
        finally:
            db.close()

    def test_create_with_rollback_source_id_persisted(self, tmp_path, monkeypatch):
        """rollback_source_id is stored and can be read back."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            original_id = uuid.uuid4().hex
            rollback_id = uuid.uuid4().hex
            calibration_orm.create_calibration_record(
                db=db,
                record_id=rollback_id,
                sensor_id="sensor-1",
                reference_sensor_id="ref-1",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used=["icp"],
                pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                rollback_source_id=original_id,
            )
            fetched = calibration_orm.get_calibration_by_id(db, rollback_id)
            assert fetched is not None
            assert fetched.rollback_source_id == original_id
        finally:
            db.close()

    def test_create_with_registration_method_persisted(self, tmp_path, monkeypatch):
        """registration_method dict is serialized to JSON and stored."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            method = {"method": "icp", "stages": ["global", "icp"]}
            record_id = uuid.uuid4().hex
            calibration_orm.create_calibration_record(
                db=db,
                record_id=record_id,
                sensor_id="sensor-1",
                reference_sensor_id="ref-1",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used=["icp"],
                pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                registration_method=method,
            )
            fetched = calibration_orm.get_calibration_by_id(db, record_id)
            assert fetched is not None
            assert json.loads(fetched.registration_method_json) == method
            # to_dict() should parse it as Python object
            d = fetched.to_dict()
            assert d["registration_method"] == method
        finally:
            db.close()


class TestUpdateCalibrationAcceptanceWithAcceptedAt:
    """Task 2.2 — update_calibration_acceptance() accepts accepted_at parameter."""

    def test_accepted_at_is_persisted(self, tmp_path, monkeypatch):
        """When accepted=True and accepted_at provided, accepted_at is stored."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            record_id = uuid.uuid4().hex
            calibration_orm.create_calibration_record(
                db=db,
                record_id=record_id,
                sensor_id="sensor-1",
                reference_sensor_id="ref-1",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used=["icp"],
                pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            )
            updated = calibration_orm.update_calibration_acceptance(
                db=db,
                record_id=record_id,
                accepted=True,
                accepted_at="2026-01-01T00:00:00Z",
            )
            assert updated is not None
            assert updated.accepted is True
            assert updated.accepted_at == "2026-01-01T00:00:00Z"
        finally:
            db.close()

    def test_accepted_at_not_set_when_not_provided(self, tmp_path, monkeypatch):
        """When accepted_at not provided, accepted_at remains None."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            record_id = uuid.uuid4().hex
            calibration_orm.create_calibration_record(
                db=db,
                record_id=record_id,
                sensor_id="sensor-1",
                reference_sensor_id="ref-1",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used=["icp"],
                pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            )
            updated = calibration_orm.update_calibration_acceptance(
                db=db,
                record_id=record_id,
                accepted=True,
            )
            assert updated is not None
            assert updated.accepted is True
            assert updated.accepted_at is None
        finally:
            db.close()


class TestGetCalibrationHistoryByNode:
    """Task 2.3 — get_calibration_history_by_node() filters by node_id."""

    def test_returns_records_for_node(self, tmp_path, monkeypatch):
        """3 records with node_id='test-node' all returned."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            for i in range(3):
                calibration_orm.create_calibration_record(
                    db=db,
                    record_id=uuid.uuid4().hex,
                    sensor_id=f"sensor-{i}",
                    reference_sensor_id="ref-1",
                    fitness=0.9,
                    rmse=0.003,
                    quality="excellent",
                    stages_used=["icp"],
                    pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                    node_id="test-node",
                )
            records = calibration_orm.get_calibration_history_by_node(db, "test-node")
            assert len(records) == 3
        finally:
            db.close()

    def test_excludes_other_nodes(self, tmp_path, monkeypatch):
        """Records with different node_id are excluded."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            calibration_orm.create_calibration_record(
                db=db,
                record_id=uuid.uuid4().hex,
                sensor_id="sensor-1",
                reference_sensor_id="ref-1",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used=["icp"],
                pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                node_id="node-A",
            )
            calibration_orm.create_calibration_record(
                db=db,
                record_id=uuid.uuid4().hex,
                sensor_id="sensor-2",
                reference_sensor_id="ref-1",
                fitness=0.9,
                rmse=0.003,
                quality="excellent",
                stages_used=["icp"],
                pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                node_id="node-B",
            )
            records = calibration_orm.get_calibration_history_by_node(db, "node-A")
            assert len(records) == 1
            assert records[0].node_id == "node-A"
        finally:
            db.close()

    def test_filters_by_run_id(self, tmp_path, monkeypatch):
        """Passing run_id further filters results."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            for run in ["run-1", "run-2"]:
                calibration_orm.create_calibration_record(
                    db=db,
                    record_id=uuid.uuid4().hex,
                    sensor_id="sensor-1",
                    reference_sensor_id="ref-1",
                    fitness=0.9,
                    rmse=0.003,
                    quality="excellent",
                    stages_used=["icp"],
                    pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                    node_id="test-node",
                    run_id=run,
                )
            records = calibration_orm.get_calibration_history_by_node(db, "test-node", run_id="run-1")
            assert len(records) == 1
            assert records[0].run_id == "run-1"
        finally:
            db.close()

    def test_respects_limit(self, tmp_path, monkeypatch):
        """limit parameter restricts number of records returned."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            for i in range(5):
                calibration_orm.create_calibration_record(
                    db=db,
                    record_id=uuid.uuid4().hex,
                    sensor_id=f"sensor-{i}",
                    reference_sensor_id="ref-1",
                    fitness=0.9,
                    rmse=0.003,
                    quality="excellent",
                    stages_used=["icp"],
                    pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                    node_id="test-node",
                )
            records = calibration_orm.get_calibration_history_by_node(db, "test-node", limit=3)
            assert len(records) == 3
        finally:
            db.close()


class TestGetCalibrationHistoryRunIdFilter:
    """Task 2.4 — get_calibration_history() supports run_id filter."""

    def test_run_id_filter_returns_matching_only(self, tmp_path, monkeypatch):
        """When run_id provided, only matching records returned."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            for run, sensor in [("run-abc", "sensor-1"), ("run-abc", "sensor-2"), ("run-xyz", "sensor-3")]:
                calibration_orm.create_calibration_record(
                    db=db,
                    record_id=uuid.uuid4().hex,
                    sensor_id=sensor,
                    reference_sensor_id="ref-1",
                    fitness=0.9,
                    rmse=0.003,
                    quality="excellent",
                    stages_used=["icp"],
                    pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                    run_id=run,
                )

            # Query sensor-1's history without run_id filter (2 records visible from sensor-1's perspective
            # but sensor_id differs - so use run_id global filter with sensor-1)
            records = calibration_orm.get_calibration_history(db, "sensor-1", run_id="run-abc")
            # sensor_id = "sensor-1" AND run_id = "run-abc" → 1 record
            assert len(records) == 1
            assert records[0].run_id == "run-abc"
            assert records[0].sensor_id == "sensor-1"
        finally:
            db.close()

    def test_without_run_id_filter_returns_all(self, tmp_path, monkeypatch):
        """When run_id is None, all records for sensor_id returned."""
        engine = make_engine(tmp_path, monkeypatch)
        db = _make_db_session(engine)
        try:
            for run in ["run-1", "run-2"]:
                calibration_orm.create_calibration_record(
                    db=db,
                    record_id=uuid.uuid4().hex,
                    sensor_id="sensor-1",
                    reference_sensor_id="ref-1",
                    fitness=0.9,
                    rmse=0.003,
                    quality="excellent",
                    stages_used=["icp"],
                    pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                    run_id=run,
                )
            records = calibration_orm.get_calibration_history(db, "sensor-1")
            assert len(records) == 2
        finally:
            db.close()
