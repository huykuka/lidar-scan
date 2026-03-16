"""
Integration tests for CalibrationNode provenance tracking through complex DAG topologies.

Tests that source_sensor_id and processing_chain are correctly propagated when
sensors feed into CalibrationNode through one or more intermediate processing nodes.

Phase 6 — Tests 1, 2, 3
"""
import pytest
import numpy as np
from collections import deque
from unittest.mock import Mock, AsyncMock, patch

from app.modules.calibration.calibration_node import CalibrationNode, BufferedFrame


class TestSimpleDirectConnection:
    """
    Test 1: Simple direct connection
    DAG: LidarSensor A → CalibrationNode
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
    async def test_source_sensor_id_is_leaf_sensor_direct(self, calibration_node):
        """source_sensor_id == A when sensor connects directly."""
        payload = {
            "lidar_id": "sensor-A",
            "node_id": "sensor-A",
            "points": np.random.rand(100, 3).astype(np.float32),
            "timestamp": 1.0,
            "processing_chain": ["sensor-A"],
        }
        await calibration_node.on_input(payload)

        assert "sensor-A" in calibration_node._frame_buffer
        frame = calibration_node._frame_buffer["sensor-A"][0]
        assert frame.source_sensor_id == "sensor-A"
        assert frame.processing_chain == ["sensor-A"]

    @pytest.mark.asyncio
    async def test_transformation_targets_leaf_sensor_direct(self, calibration_node):
        """_apply_calibration writes to leaf sensor (A), not a processing node."""
        from app.modules.calibration.history import CalibrationRecord

        record = CalibrationRecord(
            timestamp="2026-01-01T00:00:00Z",
            sensor_id="sensor-A",
            source_sensor_id="sensor-A",
            processing_chain=["sensor-A"],
            run_id="run001",
            reference_sensor_id="sensor-B",
            fitness=0.9,
            rmse=0.01,
            quality="excellent",
            stages_used=["icp"],
            pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            pose_after={"x": 0.1, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            transformation_matrix=np.eye(4).tolist(),
            accepted=False,
        )

        with patch("app.modules.calibration.calibration_node.NodeRepository") as MockRepo, \
             patch("app.modules.calibration.calibration_node.CalibrationHistory"), \
             patch("app.modules.calibration.calibration_node.SessionLocal"):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = Mock(return_value={"config": {}})
            mock_repo.update_node_config = Mock()

            await calibration_node._apply_calibration("sensor-A", record)

            call_args = mock_repo.update_node_config.call_args
            assert call_args[0][0] == "sensor-A"


class TestComplexProcessingChain:
    """
    Test 2: Complex processing chain
    DAG: LidarSensor A → CropNode → DownsampleNode → CalibrationNode
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
    async def test_source_sensor_id_is_leaf_sensor_complex_chain(self, calibration_node):
        """source_sensor_id == A even when sensor feeds through crop and downsample."""
        payload = {
            "lidar_id": "sensor-A",          # leaf sensor
            "node_id": "downsample-1",        # last processing node
            "points": np.random.rand(100, 3).astype(np.float32),
            "timestamp": 1.0,
            "processing_chain": ["sensor-A", "crop-1", "downsample-1"],
        }
        await calibration_node.on_input(payload)

        # Keyed by leaf sensor ID
        assert "sensor-A" in calibration_node._frame_buffer
        assert "downsample-1" not in calibration_node._frame_buffer
        assert "crop-1" not in calibration_node._frame_buffer

        frame = calibration_node._frame_buffer["sensor-A"][0]
        assert frame.source_sensor_id == "sensor-A"
        assert frame.processing_chain == ["sensor-A", "crop-1", "downsample-1"]
        assert frame.node_id == "downsample-1"

    @pytest.mark.asyncio
    async def test_transformation_targets_leaf_sensor_not_intermediate(self, calibration_node):
        """
        _apply_calibration must target source_sensor_id (A), NOT the intermediate
        processing nodes (crop-1 or downsample-1).
        """
        from app.modules.calibration.history import CalibrationRecord

        record = CalibrationRecord(
            timestamp="2026-01-01T00:00:00Z",
            sensor_id="downsample-1",          # wrong if used as target
            source_sensor_id="sensor-A",       # correct target
            processing_chain=["sensor-A", "crop-1", "downsample-1"],
            run_id="run002",
            reference_sensor_id="sensor-B",
            fitness=0.92,
            rmse=0.008,
            quality="excellent",
            stages_used=["global", "icp"],
            pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            pose_after={"x": 0.5, "y": 0.2, "z": 0.1, "roll": 0.0, "pitch": 0.0, "yaw": 0.3},
            transformation_matrix=np.eye(4).tolist(),
            accepted=False,
        )

        with patch("app.modules.calibration.calibration_node.NodeRepository") as MockRepo, \
             patch("app.modules.calibration.calibration_node.CalibrationHistory"), \
             patch("app.modules.calibration.calibration_node.SessionLocal"):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = Mock(return_value={"config": {}})
            mock_repo.update_node_config = Mock()

            await calibration_node._apply_calibration("downsample-1", record)

            call_args = mock_repo.update_node_config.call_args
            target_id = call_args[0][0]
            assert target_id == "sensor-A", f"Expected 'sensor-A', got '{target_id}'"
            assert target_id != "downsample-1"
            assert target_id != "crop-1"

    @pytest.mark.asyncio
    async def test_trigger_calibration_returns_correct_processing_chain(self, calibration_node):
        """trigger_calibration result includes full processing_chain from leaf to calib node."""
        ref_pts = np.random.rand(100, 3).astype(np.float32)
        src_pts = np.random.rand(100, 3).astype(np.float32)

        calibration_node._frame_buffer = {
            "sensor-B": deque([BufferedFrame(
                points=ref_pts, timestamp=1.0,
                source_sensor_id="sensor-B",
                processing_chain=["sensor-B"],
                node_id="sensor-B",
            )], maxlen=30),
            "sensor-A": deque([BufferedFrame(
                points=src_pts, timestamp=2.0,
                source_sensor_id="sensor-A",
                processing_chain=["sensor-A", "crop-1", "downsample-1"],
                node_id="downsample-1",
            )], maxlen=30),
        }
        calibration_node._reference_sensor_id = "sensor-B"
        calibration_node._source_sensor_ids = ["sensor-A"]

        with patch("app.modules.calibration.calibration_node.NodeRepository") as MockRepo:
            MockRepo.return_value.get_by_id = Mock(return_value={
                "config": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
            })
            calibration_node.icp_engine.register = AsyncMock(return_value=Mock(
                transformation=np.eye(4), fitness=0.9, rmse=0.01,
                quality="excellent", stages_used=["icp"],
            ))

            result = await calibration_node.trigger_calibration({})

        assert result["success"] is True
        sensor_result = result["results"]["sensor-A"]
        assert sensor_result["source_sensor_id"] == "sensor-A"
        assert sensor_result["processing_chain"] == ["sensor-A", "crop-1", "downsample-1"]


class TestMultiSensorCalibration:
    """
    Test 3: Multi-sensor calibration run correlation
    DAG: LidarSensor A → CalibrationNode, LidarSensor B → CalibrationNode
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
        return CalibrationNode(mock_manager, "calib-multi", config)

    @pytest.mark.asyncio
    async def test_run_id_shared_across_sensors(self, calibration_node):
        """All sensors in one trigger call share the same run_id."""
        pts = np.random.rand(100, 3).astype(np.float32)

        calibration_node._frame_buffer = {
            "sensor-A": deque([BufferedFrame(
                points=pts.copy(), timestamp=1.0,
                source_sensor_id="sensor-A",
                processing_chain=["sensor-A"],
                node_id="sensor-A",
            )], maxlen=30),
            "sensor-B": deque([BufferedFrame(
                points=pts.copy(), timestamp=2.0,
                source_sensor_id="sensor-B",
                processing_chain=["sensor-B"],
                node_id="sensor-B",
            )], maxlen=30),
            "sensor-C": deque([BufferedFrame(
                points=pts.copy(), timestamp=3.0,
                source_sensor_id="sensor-C",
                processing_chain=["sensor-C"],
                node_id="sensor-C",
            )], maxlen=30),
        }
        calibration_node._reference_sensor_id = "sensor-A"
        calibration_node._source_sensor_ids = ["sensor-B", "sensor-C"]

        with patch("app.modules.calibration.calibration_node.NodeRepository") as MockRepo:
            MockRepo.return_value.get_by_id = Mock(return_value={
                "config": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
            })
            calibration_node.icp_engine.register = AsyncMock(return_value=Mock(
                transformation=np.eye(4), fitness=0.9, rmse=0.01,
                quality="excellent", stages_used=["icp"],
            ))

            result = await calibration_node.trigger_calibration({})

        assert result["success"] is True
        assert "run_id" in result
        assert result["run_id"] is not None

        # All pending calibrations share the same run_id
        run_ids = {rec.run_id for rec in calibration_node._pending_calibration.values()}
        assert len(run_ids) == 1, f"Expected single run_id, got: {run_ids}"
        assert result["run_id"] in run_ids

    @pytest.mark.asyncio
    async def test_source_sensor_id_per_sensor_is_correct(self, calibration_node):
        """Each sensor result carries its own correct source_sensor_id."""
        pts = np.random.rand(100, 3).astype(np.float32)

        calibration_node._frame_buffer = {
            "sensor-A": deque([BufferedFrame(
                points=pts.copy(), timestamp=1.0,
                source_sensor_id="sensor-A",
                processing_chain=["sensor-A"],
                node_id="sensor-A",
            )], maxlen=30),
            "sensor-B": deque([BufferedFrame(
                points=pts.copy(), timestamp=2.0,
                source_sensor_id="sensor-B",
                processing_chain=["sensor-B", "crop-1"],
                node_id="crop-1",
            )], maxlen=30),
        }
        calibration_node._reference_sensor_id = "sensor-A"
        calibration_node._source_sensor_ids = ["sensor-B"]

        with patch("app.modules.calibration.calibration_node.NodeRepository") as MockRepo:
            MockRepo.return_value.get_by_id = Mock(return_value={
                "config": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
            })
            calibration_node.icp_engine.register = AsyncMock(return_value=Mock(
                transformation=np.eye(4), fitness=0.9, rmse=0.01,
                quality="excellent", stages_used=["icp"],
            ))

            result = await calibration_node.trigger_calibration({})

        assert result["success"] is True
        sensor_b_result = result["results"]["sensor-B"]
        assert sensor_b_result["source_sensor_id"] == "sensor-B"
