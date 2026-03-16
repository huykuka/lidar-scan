"""
Integration tests for calibration transformation patching and history query workflows.

Covers:
- Test 4: Accept calibration workflow (config updated, history saved, reload triggered)
- Test 5: Reject calibration workflow (config unchanged, pending cleared)
- Test 6: History query by source_sensor_id
- Test 7: Run correlation query

Phase 6 — Tests 4, 5, 6, 7
"""
import pytest
import numpy as np
from collections import deque
from unittest.mock import Mock, AsyncMock, patch

from app.modules.calibration.calibration_node import CalibrationNode, BufferedFrame
from app.modules.calibration.history import CalibrationRecord
from app.repositories import calibration_orm


class TestAcceptCalibrationWorkflow:
    """
    Test 4: Accept calibration workflow
    - result is 'pending' before acceptance
    - config updated to leaf sensor after acceptance
    - history record created with accepted=True
    - manager.reload_config() called
    """

    @pytest.fixture
    def mock_manager(self):
        manager = Mock()
        manager.forward_data = AsyncMock()
        manager.reload_config = AsyncMock()
        return manager

    @pytest.fixture
    def calibration_node(self, mock_manager):
        config = {"name": "calib", "max_buffered_frames": 30, "auto_save": False}
        return CalibrationNode(mock_manager, "calib-1", config)

    @pytest.fixture
    def pending_record(self):
        """A pre-built CalibrationRecord ready to be accepted."""
        return CalibrationRecord(
            timestamp="2026-01-01T00:00:00Z",
            sensor_id="sensor-A",
            source_sensor_id="sensor-A",
            processing_chain=["sensor-A"],
            run_id="run-accept-01",
            reference_sensor_id="sensor-B",
            fitness=0.95,
            rmse=0.008,
            quality="excellent",
            stages_used=["icp"],
            pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            pose_after={"x": 0.3, "y": 0.1, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.5},
            transformation_matrix=np.eye(4).tolist(),
            accepted=False,
        )

    @pytest.mark.asyncio
    async def test_pending_calibration_stored_before_accept(
        self, calibration_node, pending_record
    ):
        """After trigger, result is pending (accepted=False) and stored in _pending_calibration."""
        # Simulate what trigger_calibration() does internally
        calibration_node._pending_calibration = {"sensor-A": pending_record}

        assert "sensor-A" in calibration_node._pending_calibration
        assert calibration_node._pending_calibration["sensor-A"].accepted is False

    @pytest.mark.asyncio
    async def test_accept_writes_config_to_leaf_sensor(
        self, calibration_node, pending_record
    ):
        """Accepting calibration calls update_node_config on the leaf sensor (source_sensor_id)."""
        calibration_node._pending_calibration = {"sensor-A": pending_record}

        with patch("app.modules.calibration.calibration_node.NodeRepository") as MockRepo, \
             patch("app.modules.calibration.calibration_node.CalibrationHistory"), \
             patch("app.modules.calibration.calibration_node.SessionLocal"):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = Mock(return_value={"config": {}})
            mock_repo.update_node_config = Mock()

            await calibration_node._apply_calibration("sensor-A", pending_record)

            # config must go to leaf sensor
            call_args = mock_repo.update_node_config.call_args
            assert call_args[0][0] == "sensor-A"

            # pose_after values must be written
            written_config = call_args[0][1]
            assert written_config["x"] == pytest.approx(0.3)
            assert written_config["y"] == pytest.approx(0.1)
            assert written_config["yaw"] == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_accept_triggers_dag_reload(
        self, calibration_node, mock_manager, pending_record
    ):
        """Accepting calibration must call manager.reload_config() once."""
        calibration_node._pending_calibration = {"sensor-A": pending_record}

        with patch("app.modules.calibration.calibration_node.NodeRepository") as MockRepo, \
             patch("app.modules.calibration.calibration_node.CalibrationHistory"), \
             patch("app.modules.calibration.calibration_node.SessionLocal"):
            MockRepo.return_value.get_by_id = Mock(return_value={"config": {}})
            MockRepo.return_value.update_node_config = Mock()

            await calibration_node._apply_calibration("sensor-A", pending_record)

        mock_manager.reload_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_accept_saves_history_record(
        self, calibration_node, pending_record
    ):
        """CalibrationHistory.save_record() is invoked with the accepted record.

        CalibrationHistory.save_record is called as a class-level method, so we
        assert on MockHistory.save_record (the patched class attribute), not on
        MockHistory.return_value.save_record (an instance attribute).
        """
        calibration_node._pending_calibration = {"sensor-A": pending_record}

        with patch("app.modules.calibration.calibration_node.NodeRepository") as MockRepo, \
             patch("app.modules.calibration.calibration_node.CalibrationHistory") as MockHistory, \
             patch("app.modules.calibration.calibration_node.SessionLocal"):
            MockRepo.return_value.get_by_id = Mock(return_value={"config": {}})
            MockRepo.return_value.update_node_config = Mock()
            MockHistory.save_record = Mock()  # Class-level static/classmethod

            await calibration_node._apply_calibration("sensor-A", pending_record)

        MockHistory.save_record.assert_called_once()


class TestRejectCalibrationWorkflow:
    """
    Test 5: Reject calibration workflow
    - nodes.config_json unchanged
    - _pending_calibration is cleared
    """

    @pytest.fixture
    def mock_manager(self):
        manager = Mock()
        manager.forward_data = AsyncMock()
        manager.reload_config = AsyncMock()
        return manager

    @pytest.fixture
    def calibration_node(self, mock_manager):
        config = {"name": "calib", "max_buffered_frames": 30, "auto_save": False}
        return CalibrationNode(mock_manager, "calib-1", config)

    @pytest.mark.asyncio
    async def test_reject_clears_pending_calibration(self, calibration_node):
        """After rejection _pending_calibration is None (cleared)."""
        calibration_node._pending_calibration = {
            "sensor-A": Mock(),
            "sensor-B": Mock(),
        }

        await calibration_node.reject_calibration()

        # _pending_calibration is set back to None on rejection
        assert calibration_node._pending_calibration is None

    @pytest.mark.asyncio
    async def test_reject_does_not_call_update_node_config(self, calibration_node):
        """Rejection must NOT patch any node config."""
        calibration_node._pending_calibration = {"sensor-A": Mock()}

        with patch("app.modules.calibration.calibration_node.NodeRepository") as MockRepo:
            mock_repo = MockRepo.return_value

            await calibration_node.reject_calibration()

            mock_repo.update_node_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_does_not_call_reload_config(self, calibration_node, mock_manager):
        """Rejection must NOT trigger a DAG reload."""
        calibration_node._pending_calibration = {"sensor-A": Mock()}

        await calibration_node.reject_calibration()

        mock_manager.reload_config.assert_not_called()


class TestHistoryQueryBySourceSensorId:
    """
    Test 6: History query by source_sensor_id
    GET /api/v1/calibration/history/{sensor_id}?source_sensor_id=A
    """

    def test_get_calibration_history_by_source_returns_matching_records(self, client):
        """Records for leaf sensor A are returned when queried by source_sensor_id."""
        response = client.get("/api/v1/calibration/history/sensor-A?source_sensor_id=sensor-A")
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert data["sensor_id"] == "sensor-A"

    def test_history_endpoint_source_sensor_id_filter(self, client):
        """?source_sensor_id query param is forwarded correctly and only matching records returned."""
        # Create a node so queries are meaningful
        client.post("/api/v1/nodes", json={
            "id": "sensor-A",
            "name": "Sensor A",
            "type": "sensor",
            "category": "Input",
            "config": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        })

        # Query history filtered by source_sensor_id
        response = client.get(
            "/api/v1/calibration/history/sensor-A",
            params={"source_sensor_id": "sensor-A", "limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        # All returned records should have source_sensor_id == "sensor-A"
        for record in data.get("history", []):
            assert record.get("source_sensor_id") == "sensor-A"


class TestRunCorrelationQuery:
    """
    Test 7: Run correlation
    get_calibration_history_by_run() returns all sensors from a shared run_id.
    """

    def test_run_correlation_via_orm(self, client):
        """Records inserted with same run_id are returned together."""
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            run_id = "integration-run-007"

            # Create two records under the same run
            calibration_orm.create_calibration_record(
                db=db,
                record_id="rec-A-001",
                sensor_id="sensor-A",
                reference_sensor_id="sensor-ref",
                fitness=0.9,
                rmse=0.01,
                quality="excellent",
                stages_used=["icp"],
                pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                pose_after={"x": 0.1, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                transformation_matrix=np.eye(4).tolist(),
                source_sensor_id="sensor-A",
                processing_chain=["sensor-A"],
                run_id=run_id,
            )
            calibration_orm.create_calibration_record(
                db=db,
                record_id="rec-B-001",
                sensor_id="sensor-B",
                reference_sensor_id="sensor-ref",
                fitness=0.88,
                rmse=0.015,
                quality="good",
                stages_used=["global", "icp"],
                pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                pose_after={"x": 0.2, "y": 0.1, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.2},
                transformation_matrix=np.eye(4).tolist(),
                source_sensor_id="sensor-B",
                processing_chain=["sensor-B", "crop-1"],
                run_id=run_id,
            )

            # Query by run_id
            records = calibration_orm.get_calibration_history_by_run(db, run_id)

        assert len(records) == 2
        sensor_ids = {r.sensor_id for r in records}
        assert sensor_ids == {"sensor-A", "sensor-B"}

        # Verify run_id is set on both records
        for record in records:
            assert record.run_id == run_id

    def test_run_correlation_different_runs_isolated(self, client):
        """Records from different runs are not mixed."""
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            # Insert records in two separate runs
            for run_id, sensor_id, rec_id in [
                ("run-X", "sensor-X", "rec-X"),
                ("run-Y", "sensor-Y", "rec-Y"),
            ]:
                calibration_orm.create_calibration_record(
                    db=db,
                    record_id=rec_id,
                    sensor_id=sensor_id,
                    reference_sensor_id="sensor-ref",
                    fitness=0.85,
                    rmse=0.02,
                    quality="good",
                    stages_used=["icp"],
                    pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                    pose_after={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                    transformation_matrix=np.eye(4).tolist(),
                    source_sensor_id=sensor_id,
                    processing_chain=[sensor_id],
                    run_id=run_id,
                )

            run_x_records = calibration_orm.get_calibration_history_by_run(db, "run-X")
            run_y_records = calibration_orm.get_calibration_history_by_run(db, "run-Y")

        assert len(run_x_records) == 1
        assert run_x_records[0].sensor_id == "sensor-X"

        assert len(run_y_records) == 1
        assert run_y_records[0].sensor_id == "sensor-Y"
