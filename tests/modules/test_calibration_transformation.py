"""
Unit tests for calibration transformation patch workflow.

Tests that transformations are applied to the correct leaf sensor node.
"""
import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from app.modules.calibration.history import CalibrationRecord


class TestCalibrationTransformationPatch:
    """Test transformation patching to leaf sensor"""
    
    @pytest.fixture
    def mock_manager(self):
        """Create a mock NodeManager"""
        manager = Mock()
        manager.forward_data = AsyncMock()
        manager.reload_config = AsyncMock()
        return manager
    
    @pytest.fixture
    def calibration_node(self, mock_manager):
        """Create a CalibrationNode with mocked manager"""
        from app.modules.calibration.calibration_node import CalibrationNode
        
        config = {
            "name": "Test Calibration",
            "max_buffered_frames": 30,
            "auto_save": False
        }
        return CalibrationNode(mock_manager, "calib-node-1", config)
    
    @pytest.mark.asyncio
    async def test_apply_calibration_targets_source_sensor_id(self, calibration_node):
        """Test _apply_calibration uses source_sensor_id (leaf sensor) not processing node"""
        from unittest.mock import patch
        
        # Create a record with provenance
        record = CalibrationRecord(
            timestamp="2026-03-16T10:00:00Z",
            sensor_id="downsample-1",  # This is wrong target
            source_sensor_id="sensor-A",  # This is correct target (leaf sensor)
            processing_chain=["sensor-A", "crop-1", "downsample-1"],
            run_id="abc123",
            reference_sensor_id="sensor-B",
            fitness=0.95,
            rmse=0.01,
            quality="excellent",
            stages_used=["icp"],
            pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            pose_after={"x": 0.3, "y": 0.1, "z": 0.5, "roll": 0.2, "pitch": 0.0, "yaw": 1.5},
            transformation_matrix=[[1, 0, 0, 0.3], [0, 1, 0, 0.1], [0, 0, 1, 0.5], [0, 0, 0, 1]],
            accepted=False
        )
        
        with patch('app.modules.calibration.calibration_node.NodeRepository') as MockRepo, \
             patch('app.modules.calibration.calibration_node.CalibrationHistory') as MockHistory, \
             patch('app.modules.calibration.calibration_node.SessionLocal') as MockSession:
            
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = Mock(return_value={"config": {}})
            mock_repo_instance.update_node_pose = Mock()
            mock_db = MockSession.return_value
            
            # Call _apply_calibration
            await calibration_node._apply_calibration("downsample-1", record)
            
            # Verify update_node_pose was called with source_sensor_id (sensor-A), NOT sensor_id (downsample-1)
            mock_repo_instance.update_node_pose.assert_called_once()
            call_args = mock_repo_instance.update_node_pose.call_args
            target_id = call_args[0][0]
            
            assert target_id == "sensor-A", f"Expected target 'sensor-A', got '{target_id}'"
            assert target_id != "downsample-1", "Should NOT target processing node"
            
            # Verify pose_after was written as a Pose object
            pose_update = call_args[0][1]
            assert pose_update.x == pytest.approx(0.3)
            assert pose_update.y == pytest.approx(0.1)
            assert pose_update.z == pytest.approx(0.5)
            
            # Verify reload_config was called
            calibration_node.manager.reload_config.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_trigger_calibration_generates_run_id(self, calibration_node, mock_manager):
        """Test trigger_calibration generates run_id for correlation"""
        from unittest.mock import patch
        from app.modules.calibration.calibration_node import BufferedFrame
        from collections import deque
        
        # Setup frame buffers
        ref_points = np.random.rand(100, 3).astype(np.float32)
        src_points = np.random.rand(100, 3).astype(np.float32)
        
        calibration_node._frame_buffer = {
            "sensor-A": deque([BufferedFrame(
                points=ref_points,
                timestamp=1.0,
                source_sensor_id="sensor-A",
                processing_chain=["sensor-A"],
                node_id="sensor-A"
            )], maxlen=30),
            "sensor-B": deque([BufferedFrame(
                points=src_points,
                timestamp=2.0,
                source_sensor_id="sensor-B",
                processing_chain=["sensor-B", "crop-1"],
                node_id="crop-1"
            )], maxlen=30)
        }
        
        calibration_node._reference_sensor_id = "sensor-A"
        calibration_node._source_sensor_ids = ["sensor-B"]
        
        with patch('app.modules.calibration.calibration_node.NodeRepository') as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = Mock(return_value={
                "config": {},
                "pose": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
            })
            
            # Mock ICP engine
            calibration_node.icp_engine.register = AsyncMock(return_value=Mock(
                transformation=np.eye(4),
                fitness=0.95,
                rmse=0.01,
                quality="excellent",
                stages_used=["icp"]
            ))
            
            result = await calibration_node.trigger_calibration({})
            
            assert result["success"] is True
            assert "run_id" in result
            assert result["run_id"] is not None
            assert len(result["run_id"]) > 0
            
            # Verify all sensors in same run share the run_id
            if len(calibration_node._pending_calibration) > 0:
                run_ids = [rec.run_id for rec in calibration_node._pending_calibration.values()]
                assert len(set(run_ids)) == 1, "All sensors should share same run_id"
    
    @pytest.mark.asyncio
    async def test_trigger_calibration_includes_provenance_in_results(self, calibration_node, mock_manager):
        """Test trigger_calibration includes source_sensor_id and processing_chain in results"""
        from unittest.mock import patch
        from app.modules.calibration.calibration_node import BufferedFrame
        from collections import deque
        
        # Setup frame buffer for sensor behind processing nodes
        src_points = np.random.rand(100, 3).astype(np.float32)
        ref_points = np.random.rand(100, 3).astype(np.float32)
        
        calibration_node._frame_buffer = {
            "sensor-A": deque([BufferedFrame(
                points=src_points,
                timestamp=1.0,
                source_sensor_id="sensor-A",  # Leaf sensor
                processing_chain=["sensor-A", "crop-1", "downsample-1"],  # Full chain
                node_id="downsample-1"  # Last processing node
            )], maxlen=30),
            "sensor-B": deque([BufferedFrame(
                points=ref_points,
                timestamp=2.0,
                source_sensor_id="sensor-B",
                processing_chain=["sensor-B"],
                node_id="sensor-B"
            )], maxlen=30)
        }
        
        calibration_node._reference_sensor_id = "sensor-B"
        calibration_node._source_sensor_ids = ["sensor-A"]
        
        with patch('app.modules.calibration.calibration_node.NodeRepository') as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = Mock(return_value={
                "config": {},
                "pose": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
            })
            
            # Mock ICP engine
            calibration_node.icp_engine.register = AsyncMock(return_value=Mock(
                transformation=np.eye(4),
                fitness=0.95,
                rmse=0.01,
                quality="excellent",
                stages_used=["icp"]
            ))
            
            result = await calibration_node.trigger_calibration({})
            
            assert result["success"] is True
            assert "sensor-A" in result["results"]
            
            sensor_result = result["results"]["sensor-A"]
            assert "source_sensor_id" in sensor_result
            assert sensor_result["source_sensor_id"] == "sensor-A"
            assert "processing_chain" in sensor_result
            assert sensor_result["processing_chain"] == ["sensor-A", "crop-1", "downsample-1"]
