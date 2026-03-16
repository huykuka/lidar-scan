"""
Unit tests for calibration database schema extension (source_sensor_id, processing_chain, run_id).

Tests the CalibrationRecord dataclass and database model changes.
"""
import pytest
from dataclasses import field
from typing import List

from app.modules.calibration.history import CalibrationRecord, create_calibration_record


class TestCalibrationRecordExtension:
    """Test CalibrationRecord with new provenance fields"""
    
    def test_calibration_record_with_provenance(self):
        """Test creating CalibrationRecord with source_sensor_id, processing_chain, run_id"""
        record = CalibrationRecord(
            timestamp="2026-03-16T10:00:00Z",
            sensor_id="sensor-A",
            source_sensor_id="sensor-A",
            processing_chain=["sensor-A", "crop-1", "downsample-1"],
            run_id="abc123def456",
            reference_sensor_id="sensor-B",
            fitness=0.95,
            rmse=0.01,
            quality="excellent",
            stages_used=["global", "icp"],
            pose_before={"x": 0.0, "y": 0.0, "z": 0.5, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            pose_after={"x": 0.3, "y": 0.1, "z": 0.5, "roll": 0.2, "pitch": 0.0, "yaw": 1.5},
            transformation_matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            accepted=True,
            notes=""
        )
        
        assert record.source_sensor_id == "sensor-A"
        assert record.processing_chain == ["sensor-A", "crop-1", "downsample-1"]
        assert record.run_id == "abc123def456"
    
    def test_calibration_record_to_dict_includes_new_fields(self):
        """Test to_dict() includes source_sensor_id, processing_chain, run_id"""
        record = CalibrationRecord(
            timestamp="2026-03-16T10:00:00Z",
            sensor_id="sensor-A",
            source_sensor_id="sensor-A",
            processing_chain=["sensor-A", "crop-1"],
            run_id="abc123",
            reference_sensor_id="sensor-B",
            fitness=0.90,
            rmse=0.02,
            quality="good",
            stages_used=["icp"],
            pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            pose_after={"x": 0.1, "y": 0.1, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            transformation_matrix=[[1, 0, 0, 0.1], [0, 1, 0, 0.1], [0, 0, 1, 0], [0, 0, 0, 1]],
            accepted=False
        )
        
        data = record.to_dict()
        
        assert "source_sensor_id" in data
        assert data["source_sensor_id"] == "sensor-A"
        assert "processing_chain" in data
        assert data["processing_chain"] == ["sensor-A", "crop-1"]
        assert "run_id" in data
        assert data["run_id"] == "abc123"
    
    def test_calibration_record_from_dict_backward_compatible(self):
        """Test from_dict() handles legacy records without new fields"""
        legacy_data = {
            "timestamp": "2026-01-01T08:00:00Z",
            "sensor_id": "sensor-A",
            "reference_sensor_id": "sensor-B",
            "fitness": 0.85,
            "rmse": 0.03,
            "quality": "good",
            "stages_used": ["global", "icp"],
            "pose_before": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            "pose_after": {"x": 0.2, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            "transformation_matrix": [[1, 0, 0, 0.2], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            "accepted": True,
            "notes": ""
        }
        
        # Should not raise error even without new fields
        record = CalibrationRecord.from_dict(legacy_data)
        
        assert record.sensor_id == "sensor-A"
        assert record.fitness == 0.85
        # New fields should have defaults
        assert record.source_sensor_id == ""
        assert record.processing_chain == []
        assert record.run_id == ""
    
    def test_create_calibration_record_factory_with_provenance(self):
        """Test create_calibration_record factory includes new parameters"""
        record = create_calibration_record(
            sensor_id="sensor-A",
            source_sensor_id="sensor-A",
            processing_chain=["sensor-A", "crop-1"],
            run_id="xyz789",
            reference_sensor_id="sensor-B",
            fitness=0.92,
            rmse=0.015,
            quality="excellent",
            stages_used=["icp"],
            pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            pose_after={"x": 0.25, "y": 0.05, "z": 0.0, "roll": 0.1, "pitch": 0.0, "yaw": 1.2},
            transformation_matrix=[[1, 0, 0, 0.25], [0, 1, 0, 0.05], [0, 0, 1, 0], [0, 0, 0, 1]],
            accepted=False,
            notes="Test calibration"
        )
        
        assert record.source_sensor_id == "sensor-A"
        assert record.processing_chain == ["sensor-A", "crop-1"]
        assert record.run_id == "xyz789"
        assert record.timestamp is not None  # Factory adds timestamp
    
    def test_create_calibration_record_factory_defaults(self):
        """Test create_calibration_record factory uses defaults for new fields"""
        record = create_calibration_record(
            sensor_id="sensor-A",
            reference_sensor_id="sensor-B",
            fitness=0.90,
            rmse=0.02,
            quality="good",
            stages_used=["icp"],
            pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            pose_after={"x": 0.1, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            transformation_matrix=[[1, 0, 0, 0.1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        )
        
        # Should use defaults when not provided
        assert record.source_sensor_id == ""
        assert record.processing_chain == []
        assert record.run_id == ""


class TestCalibrationORMExtension:
    """Test calibration ORM with new query helpers"""
    
    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session"""
        from unittest.mock import Mock, MagicMock
        
        session = Mock()
        session.query = MagicMock()
        session.add = Mock()
        session.commit = Mock()
        session.refresh = Mock()
        return session
    
    def test_create_calibration_record_includes_provenance(self, mock_db_session):
        """Test calibration_orm.create_calibration_record includes new fields"""
        from app.repositories import calibration_orm
        from unittest.mock import patch
        
        with patch('app.repositories.calibration_orm.CalibrationHistoryModel') as MockModel:
            calibration_orm.create_calibration_record(
                db=mock_db_session,
                record_id="rec-123",
                sensor_id="sensor-A",
                source_sensor_id="sensor-A",
                processing_chain=["sensor-A", "crop-1"],
                run_id="run-abc",
                reference_sensor_id="sensor-B",
                fitness=0.95,
                rmse=0.01,
                quality="excellent",
                stages_used=["icp"],
                pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                pose_after={"x": 0.3, "y": 0.1, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                transformation_matrix=[[1, 0, 0, 0.3], [0, 1, 0, 0.1], [0, 0, 1, 0], [0, 0, 0, 1]],
                accepted=True
            )
            
            # Verify MockModel was called with new fields
            MockModel.assert_called_once()
            call_kwargs = MockModel.call_args.kwargs
            assert call_kwargs["source_sensor_id"] == "sensor-A"
            assert '"sensor-A", "crop-1"' in call_kwargs["processing_chain_json"]
            assert call_kwargs["run_id"] == "run-abc"
    
    def test_create_calibration_record_defaults_source_sensor_id(self, mock_db_session):
        """Test source_sensor_id defaults to sensor_id for backward compatibility"""
        from app.repositories import calibration_orm
        from unittest.mock import patch
        
        with patch('app.repositories.calibration_orm.CalibrationHistoryModel') as MockModel:
            calibration_orm.create_calibration_record(
                db=mock_db_session,
                record_id="rec-123",
                sensor_id="sensor-A",
                # source_sensor_id NOT provided
                reference_sensor_id="sensor-B",
                fitness=0.90,
                rmse=0.02,
                quality="good",
                stages_used=["icp"],
                pose_before={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                pose_after={"x": 0.1, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                transformation_matrix=[[1, 0, 0, 0.1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
            )
            
            # source_sensor_id should default to sensor_id
            call_kwargs = MockModel.call_args.kwargs
            assert call_kwargs["source_sensor_id"] == "sensor-A"
