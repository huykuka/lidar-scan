"""
TDD Tests for calibration-page-redesign — Task 6.1

Full workflow integration test:
  trigger → poll status → accept → poll status → history → rollback → history again
"""
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCalibrationWorkflow:
    """Task 6.1 — End-to-end calibration workflow via HTTP polling."""

    def _make_cal_node(self, sensor_ids=None, fitness=0.95):
        """Build a mock CalibrationNode with configurable pending state."""
        from app.modules.calibration.calibration_node import CalibrationNode

        sensor_ids = sensor_ids or ["sensor-a"]
        mock_node = MagicMock(spec=CalibrationNode)
        mock_node.id = "cal-node-1"
        mock_node.auto_save = False
        mock_node._pending_calibration = None  # starts idle

        # Pending result shape returned after trigger
        pending_result = MagicMock()
        pending_result.fitness = fitness
        pending_result.rmse = 0.002
        pending_result.quality = "excellent"
        pending_result.source_sensor_id = sensor_ids[0]
        pending_result.processing_chain = sensor_ids[:]
        pending_result.pose_before = MagicMock()
        pending_result.pose_before.to_flat_dict.return_value = {
            "x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0
        }
        pending_result.pose_after = MagicMock()
        pending_result.pose_after.to_flat_dict.return_value = {
            "x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0
        }
        pending_result.transformation_matrix = [[1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        mock_node._pending_results = {sensor_ids[0]: pending_result}

        # trigger_calibration async result
        async def fake_trigger(params):
            mock_node._pending_calibration = {sensor_ids[0]: pending_result}
            return {
                "results": {sensor_ids[0]: {"fitness": fitness, "rmse": 0.002, "quality": "excellent"}},
                "run_id": uuid.uuid4().hex,
            }
        mock_node.trigger_calibration = fake_trigger

        # get_calibration_status reflects _pending_calibration
        def get_status():
            is_pending = bool(mock_node._pending_calibration)
            results = {}
            if is_pending:
                results = {
                    sensor_ids[0]: {
                        "fitness": fitness,
                        "rmse": 0.002,
                        "quality": "excellent",
                        "quality_good": fitness >= 0.7,
                        "source_sensor_id": sensor_ids[0],
                        "processing_chain": sensor_ids[:],
                        "pose_before": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                        "pose_after": {"x": 1, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                        "transformation_matrix": [[1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                    }
                }
            return {
                "node_id": "cal-node-1",
                "node_name": "Cal Node 1",
                "enabled": True,
                "calibration_state": "pending" if is_pending else "idle",
                "quality_good": (fitness >= 0.7) if is_pending else None,
                "reference_sensor_id": "sensor-ref",
                "source_sensor_ids": sensor_ids[:],
                "buffered_frames": {s: 10 for s in sensor_ids},
                "last_calibration_time": "2026-01-01T00:00:00Z" if is_pending else None,
                "pending_results": results,
            }
        mock_node.get_calibration_status = get_status

        # accept_calibration clears pending
        async def fake_accept(sensor_ids=None, db=None):
            mock_node._pending_calibration = None
            return {"success": True, "accepted": sensor_ids or list(mock_node._pending_results.keys())}
        mock_node.accept_calibration = fake_accept

        # reject_calibration clears pending
        async def fake_reject():
            mock_node._pending_calibration = None
        mock_node.reject_calibration = fake_reject

        return mock_node

    def test_step1_trigger_returns_pending_approval_true(self, client):
        """POST /trigger → pending_approval=True when auto_save is False."""
        mock_node = self._make_cal_node()
        with patch.dict(
            __import__("app.services.nodes.instance", fromlist=["node_manager"]).node_manager.nodes,
            {"cal-node-1": mock_node}
        ):
            resp = client.post(
                "/api/v1/calibration/cal-node-1/trigger",
                json={"reference_sensor_id": "sensor-ref", "source_sensor_ids": ["sensor-a"]},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending_approval"] is True

    def test_step2_poll_status_shows_pending_after_trigger(self, client):
        """GET /status after trigger → calibration_state='pending', pending_results non-empty."""
        mock_node = self._make_cal_node()

        from app.services.nodes.instance import node_manager
        with patch.dict(node_manager.nodes, {"cal-node-1": mock_node}):
            # Trigger first to put node in pending state
            client.post(
                "/api/v1/calibration/cal-node-1/trigger",
                json={"reference_sensor_id": "sensor-ref", "source_sensor_ids": ["sensor-a"]},
            )
            # Poll status
            resp = client.get("/api/v1/calibration/cal-node-1/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["calibration_state"] == "pending"
        assert len(data["pending_results"]) > 0

    def test_step3_accept_returns_success_and_accepted_list(self, client):
        """POST /accept → success=True, accepted list non-empty."""
        mock_node = self._make_cal_node()

        from app.services.nodes.instance import node_manager
        with patch.dict(node_manager.nodes, {"cal-node-1": mock_node}):
            # Trigger to set pending state
            client.post(
                "/api/v1/calibration/cal-node-1/trigger",
                json={"reference_sensor_id": "sensor-ref", "source_sensor_ids": ["sensor-a"]},
            )
            # Accept
            resp = client.post("/api/v1/calibration/cal-node-1/accept", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["accepted"]) > 0

    def test_step4_poll_status_shows_idle_after_accept(self, client):
        """GET /status after accept → calibration_state='idle'."""
        mock_node = self._make_cal_node()

        from app.services.nodes.instance import node_manager
        with patch.dict(node_manager.nodes, {"cal-node-1": mock_node}):
            client.post(
                "/api/v1/calibration/cal-node-1/trigger",
                json={"reference_sensor_id": "sensor-ref", "source_sensor_ids": ["sensor-a"]},
            )
            client.post("/api/v1/calibration/cal-node-1/accept", json={})
            resp = client.get("/api/v1/calibration/cal-node-1/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["calibration_state"] == "idle"

    def test_step5_history_shows_accepted_record_with_accepted_at(self, client):
        """GET /history/{sensor_id} → 1 record with accepted=True and accepted_at set."""
        from app.repositories.calibration_orm import create_calibration_record
        from app.db.session import SessionLocal

        record_id = uuid.uuid4().hex

        # Patch get_calibration_history to return a record with all new fields
        mock_record = MagicMock()
        mock_record.to_dict.return_value = {
            "id": record_id,
            "sensor_id": "sensor-a",
            "timestamp": "2026-01-01T00:00:00Z",
            "accepted": True,
            "accepted_at": "2026-01-01T00:01:00Z",
            "node_id": "cal-node-1",
            "rollback_source_id": None,
        }

        with patch(
            "app.api.v1.calibration.service.calibration_orm.get_calibration_history",
            return_value=[mock_record],
        ):
            resp = client.get("/api/v1/calibration/history/sensor-a")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["history"]) == 1
        record = data["history"][0]
        assert record["accepted"] is True
        assert record["accepted_at"] == "2026-01-01T00:01:00Z"

    def test_step6_rollback_returns_success_and_new_record_id(self, client):
        """POST /rollback/{sensor_id} with record_id → success=True, new_record_id returned."""
        record_id = uuid.uuid4().hex
        mock_db_record = MagicMock()
        mock_db_record.accepted = True
        mock_db_record.timestamp = "2026-01-01T00:00:00Z"
        mock_db_record.sensor_id = "sensor-a"
        mock_db_record.reference_sensor_id = "sensor-ref"
        mock_db_record.fitness = 0.95
        mock_db_record.rmse = 0.002
        mock_db_record.quality = "excellent"
        mock_db_record.node_id = "cal-node-1"
        mock_db_record.source_sensor_id = "sensor-a"
        mock_db_record.pose_after_json = json.dumps(
            {"x": 1.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        )
        mock_db_record.stages_used_json = json.dumps(["global", "icp"])
        mock_db_record.transformation_matrix_json = json.dumps(
            [[1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        )

        mock_existing_node = {
            "id": "sensor-a",
            "pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
        }

        with (
            patch("app.api.v1.calibration.service.calibration_orm.get_calibration_by_id", return_value=mock_db_record),
            patch("app.api.v1.calibration.service.calibration_orm.create_calibration_record"),
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
        assert "new_record_id" in data
        assert len(data["new_record_id"]) > 0

    def test_step7_history_after_rollback_has_two_records_with_rollback_source(self, client):
        """After rollback, history contains 2 records; second has rollback_source_id set."""
        original_record_id = uuid.uuid4().hex
        rollback_record_id = uuid.uuid4().hex

        mock_original = MagicMock()
        mock_original.to_dict.return_value = {
            "id": original_record_id,
            "sensor_id": "sensor-a",
            "timestamp": "2026-01-01T00:00:00Z",
            "accepted": True,
            "accepted_at": "2026-01-01T00:01:00Z",
            "rollback_source_id": None,
        }

        mock_rollback = MagicMock()
        mock_rollback.to_dict.return_value = {
            "id": rollback_record_id,
            "sensor_id": "sensor-a",
            "timestamp": "2026-01-01T01:00:00Z",
            "accepted": True,
            "accepted_at": "2026-01-01T01:00:00Z",
            "rollback_source_id": original_record_id,
        }

        with patch(
            "app.api.v1.calibration.service.calibration_orm.get_calibration_history",
            return_value=[mock_rollback, mock_original],
        ):
            resp = client.get("/api/v1/calibration/history/sensor-a?limit=10")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["history"]) == 2
        # Newest first — rollback record has rollback_source_id
        assert data["history"][0]["rollback_source_id"] == original_record_id
        # Original record has no rollback_source_id
        assert data["history"][1]["rollback_source_id"] is None


class TestCalibrationStatusIdle:
    """Task 6.2 coverage via API endpoint — status is idle when nothing pending."""

    def test_status_idle_state_structure(self, client):
        """GET /status on idle node → all expected fields with idle defaults."""
        from app.modules.calibration.calibration_node import CalibrationNode
        from app.services.nodes.instance import node_manager

        mock_node = MagicMock(spec=CalibrationNode)
        mock_node.get_calibration_status.return_value = {
            "node_id": "cal-node-1",
            "node_name": "Cal Node 1",
            "enabled": True,
            "calibration_state": "idle",
            "quality_good": None,
            "reference_sensor_id": None,
            "source_sensor_ids": [],
            "buffered_frames": {},
            "last_calibration_time": None,
            "pending_results": {},
        }

        with patch.dict(node_manager.nodes, {"cal-node-1": mock_node}):
            resp = client.get("/api/v1/calibration/cal-node-1/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["calibration_state"] == "idle"
        assert data["quality_good"] is None
        assert data["pending_results"] == {}
