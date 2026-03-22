"""
TDD Tests for calibration-page-redesign backend changes.

Group 3: CalibrationNode changes
- Task 3.1: get_calibration_status() method
- Task 3.2: sample_frames default fix
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.schemas.pose import Pose


# ---------------------------------------------------------------------------
# Minimal stubs for CalibrationRecord and CalibrationNode
# ---------------------------------------------------------------------------

@dataclass
class _MockCalibrationRecord:
    """Minimal stub for CalibrationRecord."""
    sensor_id: str
    reference_sensor_id: str
    fitness: float
    rmse: float
    quality: str
    stages_used: List[str]
    pose_before: Pose
    pose_after: Pose
    transformation_matrix: List[List[float]]
    accepted: bool = False
    notes: str = ""
    source_sensor_id: str = ""
    processing_chain: Optional[List[str]] = None
    run_id: str = ""
    timestamp: str = "2026-01-01T00:00:00Z"

    def __post_init__(self):
        if self.processing_chain is None:
            self.processing_chain = []


def _make_mock_record(fitness: float = 0.95, sensor_id: str = "sensor-a") -> _MockCalibrationRecord:
    return _MockCalibrationRecord(
        sensor_id=sensor_id,
        reference_sensor_id="ref-sensor",
        fitness=fitness,
        rmse=0.002,
        quality="excellent" if fitness >= 0.9 else "poor",
        stages_used=["global", "icp"],
        pose_before=Pose(x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0),
        pose_after=Pose(x=1.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0),
        transformation_matrix=[[1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
        source_sensor_id=sensor_id,
    )


def _make_calibration_node(pending: Optional[Dict[str, Any]] = None):
    """Create a CalibrationNode instance with mocked manager for testing."""
    from app.modules.calibration.calibration_node import CalibrationNode

    manager = MagicMock()
    manager.forward_data = AsyncMock()
    manager.reload_config = AsyncMock()

    node = CalibrationNode(
        manager=manager,
        node_id="cal-node-001",
        config={
            "name": "Test Calibration Node",
            "min_fitness_to_save": 0.8,
            "auto_save": False,
        },
    )

    if pending is not None:
        node._pending_calibration = pending

    return node


# ---------------------------------------------------------------------------
# Task 3.1: get_calibration_status()
# ---------------------------------------------------------------------------

class TestGetCalibrationStatus:
    """Task 3.1 — get_calibration_status() returns full workflow state."""

    def test_idle_when_no_pending_calibration(self):
        """No pending calibration → calibration_state='idle', quality_good=None, pending_results={}."""
        node = _make_calibration_node(pending=None)
        status = node.get_calibration_status()

        assert status["calibration_state"] == "idle"
        assert status["quality_good"] is None
        assert status["pending_results"] == {}

    def test_pending_when_pending_calibration_exists(self):
        """Pending calibration → calibration_state='pending'."""
        record = _make_mock_record(fitness=0.95)
        node = _make_calibration_node(pending={"sensor-a": record})

        status = node.get_calibration_status()
        assert status["calibration_state"] == "pending"

    def test_quality_good_true_when_all_fitness_above_threshold(self):
        """All results above min_fitness_to_save → quality_good=True."""
        record = _make_mock_record(fitness=0.95)
        node = _make_calibration_node(pending={"sensor-a": record})

        status = node.get_calibration_status()
        assert status["quality_good"] is True

    def test_quality_good_false_when_any_fitness_below_threshold(self):
        """Any result below min_fitness_to_save → quality_good=False."""
        record = _make_mock_record(fitness=0.3)
        node = _make_calibration_node(pending={"sensor-a": record})

        status = node.get_calibration_status()
        assert status["quality_good"] is False

    def test_pending_results_contain_required_fields(self):
        """pending_results entries have all required fields."""
        record = _make_mock_record(fitness=0.95)
        node = _make_calibration_node(pending={"sensor-a": record})

        status = node.get_calibration_status()
        assert "sensor-a" in status["pending_results"]
        result = status["pending_results"]["sensor-a"]

        required_fields = [
            "fitness", "rmse", "quality", "quality_good",
            "source_sensor_id", "processing_chain",
            "pose_before", "pose_after", "transformation_matrix",
        ]
        for field_name in required_fields:
            assert field_name in result, f"Missing field: {field_name}"

    def test_pending_results_quality_good_per_sensor(self):
        """quality_good in pending_results matches per-sensor threshold."""
        good_record = _make_mock_record(fitness=0.95, sensor_id="sensor-a")
        bad_record = _make_mock_record(fitness=0.3, sensor_id="sensor-b")
        node = _make_calibration_node(
            pending={"sensor-a": good_record, "sensor-b": bad_record}
        )

        status = node.get_calibration_status()
        assert status["pending_results"]["sensor-a"]["quality_good"] is True
        assert status["pending_results"]["sensor-b"]["quality_good"] is False

    def test_status_includes_node_metadata(self):
        """Status includes node_id, node_name, enabled, reference/source sensors."""
        node = _make_calibration_node(pending=None)
        node._reference_sensor_id = "ref-sensor"
        node._source_sensor_ids = ["sensor-a", "sensor-b"]

        status = node.get_calibration_status()
        assert status["node_id"] == "cal-node-001"
        assert status["node_name"] == "Test Calibration Node"
        assert status["enabled"] is True
        assert status["reference_sensor_id"] == "ref-sensor"
        assert status["source_sensor_ids"] == ["sensor-a", "sensor-b"]

    def test_buffered_frames_count_present(self):
        """buffered_frames returns frame count per sensor."""
        from collections import deque
        import numpy as np
        from app.modules.calibration.calibration_node import BufferedFrame

        node = _make_calibration_node(pending=None)
        buf = deque(maxlen=30)
        frame = BufferedFrame(
            points=np.zeros((10, 3)),
            timestamp=0.0,
            source_sensor_id="sensor-a",
            processing_chain=["sensor-a"],
            node_id="sensor-a",
        )
        buf.append(frame)
        node._frame_buffer["sensor-a"] = buf

        status = node.get_calibration_status()
        assert status["buffered_frames"]["sensor-a"] == 1

    def test_does_not_modify_state(self):
        """get_calibration_status() must be a pure read — no state mutation."""
        record = _make_mock_record(fitness=0.95)
        node = _make_calibration_node(pending={"sensor-a": record})

        before = node._pending_calibration
        node.get_calibration_status()
        after = node._pending_calibration

        assert before is after  # Same object, not cleared


# ---------------------------------------------------------------------------
# Task 3.2: sample_frames default fix
# ---------------------------------------------------------------------------

class TestSampleFramesDefault:
    """Task 3.2 — TriggerCalibrationRequest.sample_frames defaults to 5."""

    def test_trigger_request_default_sample_frames_is_5(self):
        """TriggerCalibrationRequest() with no args has sample_frames=5."""
        from app.api.v1.calibration.dto import TriggerCalibrationRequest
        req = TriggerCalibrationRequest()
        assert req.sample_frames == 5

    def test_trigger_request_explicit_sample_frames(self):
        """Explicit sample_frames overrides default."""
        from app.api.v1.calibration.dto import TriggerCalibrationRequest
        req = TriggerCalibrationRequest(sample_frames=10)
        assert req.sample_frames == 10
