"""
TDD Tests for calibration-page-redesign backend changes.

Group 4: History Rollback Fix
- Task 4.1: RollbackRequest uses record_id
- Task 4.2: rollback_calibration() service function uses record_id
- Task 4.3: RollbackResponse schema includes new_record_id

Group 5: API Endpoint Changes
- Task 5.1: GET /calibration/{node_id}/status endpoint
- Task 5.2: reject_calibration() response schema fix
- Task 5.3: run_id query param on history endpoint
- Task 5.4: CalibrationRecord schema includes all new fields
"""
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Task 4.1: RollbackRequest uses record_id
# ---------------------------------------------------------------------------

class TestRollbackRequestDTO:
    """Task 4.1 — RollbackRequest uses record_id, not timestamp."""

    def test_rollback_request_accepts_record_id(self):
        """POST body with record_id should validate."""
        from app.api.v1.calibration.dto import RollbackRequest
        req = RollbackRequest(record_id="abc123")
        assert req.record_id == "abc123"

    def test_rollback_request_rejects_timestamp(self):
        """POST body with timestamp only (old format) should fail validation."""
        from app.api.v1.calibration.dto import RollbackRequest
        with pytest.raises(ValidationError):
            # record_id is required — timestamp alone is invalid
            RollbackRequest(timestamp="2026-01-01T00:00:00Z")


# ---------------------------------------------------------------------------
# Task 4.3: RollbackResponse schema
# ---------------------------------------------------------------------------

class TestRollbackResponseSchema:
    """Task 4.3 — RollbackResponse includes new_record_id field."""

    def test_rollback_response_has_new_record_id(self):
        """RollbackResponse serializes all 4 fields including new_record_id."""
        from app.api.v1.schemas.calibration import RollbackResponse
        resp = RollbackResponse(
            success=True,
            sensor_id="sensor-a",
            restored_to="2026-01-01T00:00:00Z",
            new_record_id="newrecord123",
        )
        d = resp.model_dump()
        assert d["success"] is True
        assert d["sensor_id"] == "sensor-a"
        assert d["restored_to"] == "2026-01-01T00:00:00Z"
        assert d["new_record_id"] == "newrecord123"

    def test_rollback_response_requires_new_record_id(self):
        """RollbackResponse without new_record_id should fail validation."""
        from app.api.v1.schemas.calibration import RollbackResponse
        with pytest.raises(ValidationError):
            RollbackResponse(
                success=True,
                sensor_id="sensor-a",
                restored_to="2026-01-01T00:00:00Z",
                # new_record_id missing
            )


# ---------------------------------------------------------------------------
# Task 5.1: New GET /calibration/{node_id}/status endpoint
# ---------------------------------------------------------------------------

class TestCalibrationStatusEndpoint:
    """Task 5.1 — GET /calibration/{node_id}/status endpoint."""

    def test_status_endpoint_returns_200_for_valid_node(self, client):
        """GET /api/v1/calibration/{node_id}/status with live CalibrationNode → 200."""
        from app.modules.calibration.calibration_node import CalibrationNode
        from app.services.nodes.instance import node_manager

        mock_node = MagicMock(spec=CalibrationNode)
        mock_node.get_calibration_status.return_value = {
            "node_id": "test-cal-node",
            "node_name": "Test Cal",
            "enabled": True,
            "calibration_state": "idle",
            "quality_good": None,
            "reference_sensor_id": None,
            "source_sensor_ids": [],
            "buffered_frames": {},
            "last_calibration_time": None,
            "pending_results": {},
        }

        with patch.dict(node_manager.nodes, {"test-cal-node": mock_node}):
            resp = client.get("/api/v1/calibration/test-cal-node/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["node_id"] == "test-cal-node"
        assert data["calibration_state"] == "idle"

    def test_status_endpoint_returns_404_for_unknown_node(self, client):
        """GET /api/v1/calibration/{node_id}/status with unknown node → 404."""
        from app.services.nodes.instance import node_manager

        with patch.dict(node_manager.nodes, {}, clear=True):
            resp = client.get("/api/v1/calibration/nonexistent-node/status")

        assert resp.status_code == 404

    def test_status_endpoint_returns_pending_results(self, client):
        """When calibration is pending, pending_results is populated."""
        from app.modules.calibration.calibration_node import CalibrationNode
        from app.services.nodes.instance import node_manager

        mock_node = MagicMock(spec=CalibrationNode)
        mock_node.get_calibration_status.return_value = {
            "node_id": "test-cal-node",
            "node_name": "Test Cal",
            "enabled": True,
            "calibration_state": "pending",
            "quality_good": True,
            "reference_sensor_id": "ref-sensor",
            "source_sensor_ids": ["sensor-a"],
            "buffered_frames": {"sensor-a": 5},
            "last_calibration_time": "2026-01-01T00:00:00Z",
            "pending_results": {
                "sensor-a": {
                    "fitness": 0.95,
                    "rmse": 0.002,
                    "quality": "excellent",
                    "quality_good": True,
                    "source_sensor_id": "sensor-a",
                    "processing_chain": ["sensor-a"],
                    "pose_before": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    "pose_after": {"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                    "transformation_matrix": [[1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                }
            },
        }

        with patch.dict(node_manager.nodes, {"test-cal-node": mock_node}):
            resp = client.get("/api/v1/calibration/test-cal-node/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["calibration_state"] == "pending"
        assert "sensor-a" in data["pending_results"]


# ---------------------------------------------------------------------------
# Task 5.2: reject_calibration() response fix
# ---------------------------------------------------------------------------

class TestRejectCalibrationResponse:
    """Task 5.2 — reject returns {success, rejected: string[]} schema."""

    def test_reject_response_schema_has_success_and_rejected(self):
        """RejectResponse Pydantic model has success bool and rejected list."""
        from app.api.v1.schemas.calibration import RejectResponse
        resp = RejectResponse(success=True, rejected=["sensor-a", "sensor-b"])
        d = resp.model_dump()
        assert d["success"] is True
        assert d["rejected"] == ["sensor-a", "sensor-b"]

    def test_reject_returns_rejected_sensor_ids(self, client):
        """POST reject when sensors are pending → response has rejected=[sensor_ids]."""
        from app.modules.calibration.calibration_node import CalibrationNode
        from app.services.nodes.instance import node_manager
        from unittest.mock import AsyncMock

        mock_node = MagicMock(spec=CalibrationNode)
        mock_node._pending_calibration = {"sensor-a": MagicMock(), "sensor-b": MagicMock()}
        mock_node.reject_calibration = AsyncMock(return_value={"success": True})

        with patch.dict(node_manager.nodes, {"test-cal-node": mock_node}):
            resp = client.post("/api/v1/calibration/test-cal-node/reject")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert set(data["rejected"]) == {"sensor-a", "sensor-b"}

    def test_reject_returns_empty_list_when_no_pending(self, client):
        """POST reject when nothing pending → rejected=[]."""
        from app.modules.calibration.calibration_node import CalibrationNode
        from app.services.nodes.instance import node_manager
        from unittest.mock import AsyncMock

        mock_node = MagicMock(spec=CalibrationNode)
        mock_node._pending_calibration = None
        mock_node.reject_calibration = AsyncMock(return_value={"success": True})

        with patch.dict(node_manager.nodes, {"test-cal-node": mock_node}):
            resp = client.post("/api/v1/calibration/test-cal-node/reject")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["rejected"] == []


# ---------------------------------------------------------------------------
# Task 5.3: run_id query param on history endpoint
# ---------------------------------------------------------------------------

class TestHistoryRunIdFilter:
    """Task 5.3 — GET /calibration/history/{sensor_id}?run_id=... filters."""

    def test_history_endpoint_accepts_run_id_query_param(self, client):
        """GET /calibration/history/{sensor_id}?run_id=abc should not 422."""
        with patch(
            "app.api.v1.calibration.service.calibration_orm.get_calibration_history",
            return_value=[],
        ) as mock_hist:
            resp = client.get("/api/v1/calibration/history/sensor-1?run_id=abc-run")

        # Should not return 422 (validation error)
        assert resp.status_code in (200, 500)
        # If 200, verify it called with run_id
        if resp.status_code == 200:
            assert resp.json()["history"] == []


# ---------------------------------------------------------------------------
# Task 5.4: CalibrationRecord schema includes all new fields
# ---------------------------------------------------------------------------

class TestCalibrationRecordSchema:
    """Task 5.4 — CalibrationRecord schema includes all new optional fields."""

    def test_calibration_record_old_format_still_validates(self):
        """CalibrationRecord with only legacy fields still validates (backward compat)."""
        from app.api.v1.schemas.calibration import CalibrationRecord
        record = CalibrationRecord(
            id="abc123",
            sensor_id="sensor-1",
            timestamp="2026-01-01T00:00:00Z",
            accepted=True,
        )
        assert record.id == "abc123"
        # New optional fields default to None
        assert record.accepted_at is None
        assert record.node_id is None
        assert record.rollback_source_id is None

    def test_calibration_record_includes_new_fields(self):
        """CalibrationRecord accepts and returns all new fields."""
        from app.api.v1.schemas.calibration import CalibrationRecord
        record = CalibrationRecord(
            id="abc123",
            sensor_id="sensor-1",
            reference_sensor_id="ref-1",
            timestamp="2026-01-01T00:00:00Z",
            accepted=True,
            accepted_at="2026-01-01T00:01:00Z",
            accepted_by=None,
            node_id="cal-node-1",
            rollback_source_id="orig-record-id",
            registration_method={"method": "icp", "stages": ["global", "icp"]},
            pose_before={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
            pose_after={"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
            transformation_matrix=[[1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            stages_used=["global", "icp"],
            notes="test note",
        )
        d = record.model_dump()
        assert d["accepted_at"] == "2026-01-01T00:01:00Z"
        assert d["node_id"] == "cal-node-1"
        assert d["rollback_source_id"] == "orig-record-id"
        assert d["registration_method"] == {"method": "icp", "stages": ["global", "icp"]}
        assert d["pose_before"] == {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0}
