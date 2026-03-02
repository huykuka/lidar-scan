"""
Calibration history tracking and management.

This module provides data structures and utilities for tracking calibration
attempts, storing history, and enabling rollback to previous calibrations.
"""
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional
import json


@dataclass
class CalibrationRecord:
    """
    Complete record of a single calibration attempt.
    
    This is stored in the database and used for history/rollback.
    """
    timestamp: str  # ISO 8601 UTC timestamp
    sensor_id: str  # Source sensor being calibrated
    reference_sensor_id: str  # Target/reference sensor
    
    # Registration quality
    fitness: float
    rmse: float
    quality: str  # "excellent", "good", "poor"
    stages_used: List[str]  # ["global", "icp"] or ["icp"]
    
    # Pose before calibration
    pose_before: Dict[str, float]  # {x, y, z, roll, pitch, yaw}
    
    # Pose after calibration
    pose_after: Dict[str, float]  # {x, y, z, roll, pitch, yaw}
    
    # Transform applied (4x4 matrix as nested list for JSON serialization)
    transformation_matrix: List[List[float]]
    
    # User metadata
    accepted: bool  # Did user save this calibration?
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalibrationRecord":
        """Create from dictionary"""
        return cls(**data)


class CalibrationHistory:
    """
    Manages calibration history storage and retrieval.
    
    This class provides an interface to the database ORM for calibration history.
    """
    
    @staticmethod
    def save_record(record: CalibrationRecord, db_session):
        """
        Store calibration record in database.
        
        Args:
            record: CalibrationRecord to save
            db_session: SQLAlchemy session
        """
        from app.repositories import calibration_orm
        import uuid
        
        calibration_orm.create_calibration_record(
            db=db_session,
            record_id=uuid.uuid4().hex,
            sensor_id=record.sensor_id,
            reference_sensor_id=record.reference_sensor_id,
            fitness=record.fitness,
            rmse=record.rmse,
            quality=record.quality,
            stages_used=record.stages_used,
            pose_before=record.pose_before,
            pose_after=record.pose_after,
            transformation_matrix=record.transformation_matrix,
            accepted=record.accepted,
            notes=record.notes
        )
    
    @staticmethod
    def get_history(sensor_id: str, limit: int = 10, db_session=None) -> List[CalibrationRecord]:
        """
        Retrieve calibration history for a sensor.
        
        Args:
            sensor_id: Sensor node ID
            limit: Maximum number of records to return (default: 10)
            db_session: SQLAlchemy session (if None, creates temporary session)
            
        Returns:
            List of CalibrationRecords, newest first
        """
        from app.repositories import calibration_orm
        from app.db.session import SessionLocal
        
        db = db_session or SessionLocal()
        try:
            models = calibration_orm.get_calibration_history(db, sensor_id, limit)
            return [CalibrationRecord.from_dict(m.to_dict()) for m in models]
        finally:
            if db_session is None:
                db.close()
    
    @staticmethod
    def get_record_by_timestamp(sensor_id: str, timestamp: str) -> Optional[CalibrationRecord]:
        """
        Get a specific calibration record by timestamp.
        
        Args:
            sensor_id: Sensor node ID
            timestamp: ISO 8601 timestamp
            
        Returns:
            CalibrationRecord if found, None otherwise
        """
        history = CalibrationHistory.get_history(sensor_id, limit=100)
        
        for record in history:
            if record.timestamp == timestamp:
                return record
        
        return None
    
    @staticmethod
    async def rollback_to(sensor_id: str, timestamp: str):
        """
        Restore sensor pose to a previous calibration state.
        
        Args:
            sensor_id: Sensor to rollback
            timestamp: Timestamp of calibration to restore
            
        Raises:
            ValueError: If calibration record not found
        """
        from app.repositories.node_orm import NodeRepository
        
        # Find the record
        record = CalibrationHistory.get_record_by_timestamp(sensor_id, timestamp)
        
        if not record:
            raise ValueError(f"Calibration record not found for timestamp {timestamp}")
        
        # Update sensor config with pose_after from that calibration
        repo = NodeRepository()
        repo.update_node_config(sensor_id, record.pose_after)


def create_calibration_record(
    sensor_id: str,
    reference_sensor_id: str,
    fitness: float,
    rmse: float,
    quality: str,
    stages_used: List[str],
    pose_before: Dict[str, float],
    pose_after: Dict[str, float],
    transformation_matrix: List[List[float]],
    accepted: bool = False,
    notes: str = ""
) -> CalibrationRecord:
    """
    Factory function to create a CalibrationRecord with current timestamp.
    
    Args:
        sensor_id: Source sensor being calibrated
        reference_sensor_id: Target/reference sensor
        fitness: Registration fitness score
        rmse: Registration RMSE
        quality: Quality classification
        stages_used: Registration stages used
        pose_before: Pose before calibration
        pose_after: Pose after calibration
        transformation_matrix: 4x4 transformation matrix
        accepted: Whether calibration was accepted
        notes: Optional user notes
        
    Returns:
        CalibrationRecord with current timestamp
    """
    return CalibrationRecord(
        timestamp=datetime.utcnow().isoformat(),
        sensor_id=sensor_id,
        reference_sensor_id=reference_sensor_id,
        fitness=fitness,
        rmse=rmse,
        quality=quality,
        stages_used=stages_used,
        pose_before=pose_before,
        pose_after=pose_after,
        transformation_matrix=transformation_matrix,
        accepted=accepted,
        notes=notes
    )
