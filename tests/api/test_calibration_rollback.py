"""
TDD Tests for calibration-page-redesign — Task 6.3

Unit tests for rollback endpoint using record_id (not timestamp).
"""
import json
import uuid
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestRollbackWithRecordId:
    """Task 6.3 — Rollback endpoint uses record_id for lookup."""

    def _make_mock_db_record(self, accepted: bool = True, record_id: str = None):
        """Helper to create a mock CalibrationHistoryModel row."""
        mock = MagicMock()
        mock.record_id = record_id or uuid.uuid4().hex
        mock.accepted = accepted
        mock.timestamp = "2026-01-01T00:00:00+00:00"
        mock.sensor_id = "sensor-a"
        mock.reference_sensor_id = "sensor-ref"
        mock.fitness = 0.95
        mock.rmse = 0.002
        mock.quality = "excellent"
        mock.node_id = "cal-node-1"
        mock.source_sensor_id = "sensor-a"
        mock.pose_after_json = json.dumps(
            {"x": 1.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        )
        mock.stages_used_json = json.dumps(["global", "icp"])
        mock.transformation_matrix_json = json.dumps(
            [[1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        )
        return mock

    def test_valid_record_id_returns_200_with_new_record_id(self, client):
        """POST /rollback/{sensor_id} with valid accepted record_id → 200 + new_record_id."""
        record_id = uuid.uuid4().hex
        mock_record = self._make_mock_db_record(accepted=True, record_id=record_id)

        mock_existing_node = {"id": "sensor-a", "pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0}}

        with (
            patch("app.api.v1.calibration.service.calibration_orm.get_calibration_by_id", return_value=mock_record),
            patch("app.api.v1.calibration.service.calibration_orm.create_calibration_record", return_value=None),
            patch("app.api.v1.calibration.service.NodeRepository") as MockRepo,
            patch("app.api.v1.calibration.service.node_manager.reload_config", new_callable=AsyncMock),
        ):
            MockRepo.return_value.get_by_id.return_value = mock_existing_node
            MockRepo.return_value.update_node_pose.return_value = None

            resp = client.post(
                "/api/v1/calibration/rollback/sensor-a",
                json={"record_id": record_id},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["sensor_id"] == "sensor-a"
        assert "new_record_id" in data
        assert len(data["new_record_id"]) > 0

    def test_nonexistent_record_id_returns_404(self, client):
        """POST /rollback/{sensor_id} with unknown record_id → 404."""
        with patch(
            "app.api.v1.calibration.service.calibration_orm.get_calibration_by_id",
            return_value=None,
        ):
            resp = client.post(
                "/api/v1/calibration/rollback/sensor-a",
                json={"record_id": "does-not-exist"},
            )

        assert resp.status_code == 404

    def test_non_accepted_record_id_returns_400(self, client):
        """POST /rollback/{sensor_id} with unaccepted record → 400."""
        record_id = uuid.uuid4().hex
        mock_record = self._make_mock_db_record(accepted=False, record_id=record_id)

        with patch(
            "app.api.v1.calibration.service.calibration_orm.get_calibration_by_id",
            return_value=mock_record,
        ):
            resp = client.post(
                "/api/v1/calibration/rollback/sensor-a",
                json={"record_id": record_id},
            )

        assert resp.status_code == 400
        assert "not accepted" in resp.json()["detail"]

    def test_old_timestamp_body_returns_422(self, client):
        """POST /rollback/{sensor_id} with old {timestamp: ...} body → 422 Pydantic error."""
        resp = client.post(
            "/api/v1/calibration/rollback/sensor-a",
            json={"timestamp": "2026-01-01T00:00:00Z"},
        )
        # record_id is required; timestamp alone is invalid → 422 Unprocessable Entity
        assert resp.status_code == 422

    def test_rollback_response_includes_restored_to_timestamp(self, client):
        """Rollback response restored_to matches the original record's timestamp."""
        record_id = uuid.uuid4().hex
        mock_record = self._make_mock_db_record(accepted=True, record_id=record_id)
        expected_timestamp = mock_record.timestamp

        mock_existing_node = {"id": "sensor-a", "pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0}}

        with (
            patch("app.api.v1.calibration.service.calibration_orm.get_calibration_by_id", return_value=mock_record),
            patch("app.api.v1.calibration.service.calibration_orm.create_calibration_record", return_value=None),
            patch("app.api.v1.calibration.service.NodeRepository") as MockRepo,
            patch("app.api.v1.calibration.service.node_manager.reload_config", new_callable=AsyncMock),
        ):
            MockRepo.return_value.get_by_id.return_value = mock_existing_node
            MockRepo.return_value.update_node_pose.return_value = None

            resp = client.post(
                "/api/v1/calibration/rollback/sensor-a",
                json={"record_id": record_id},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["restored_to"] == expected_timestamp

    def test_rollback_creates_new_record_with_rollback_source_id(self, client):
        """Rollback calls create_calibration_record with rollback_source_id set to original record_id."""
        record_id = uuid.uuid4().hex
        mock_record = self._make_mock_db_record(accepted=True, record_id=record_id)

        mock_existing_node = {"id": "sensor-a", "pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0}}

        with (
            patch("app.api.v1.calibration.service.calibration_orm.get_calibration_by_id", return_value=mock_record),
            patch("app.api.v1.calibration.service.calibration_orm.create_calibration_record") as mock_create,
            patch("app.api.v1.calibration.service.NodeRepository") as MockRepo,
            patch("app.api.v1.calibration.service.node_manager.reload_config", new_callable=AsyncMock),
        ):
            MockRepo.return_value.get_by_id.return_value = mock_existing_node
            MockRepo.return_value.update_node_pose.return_value = None

            resp = client.post(
                "/api/v1/calibration/rollback/sensor-a",
                json={"record_id": record_id},
            )

        assert resp.status_code == 200
        # Verify create_calibration_record was called with rollback_source_id = original record_id
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["rollback_source_id"] == record_id
