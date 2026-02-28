"""
Repository for calibration history database operations.

Provides CRUD operations for storing and retrieving calibration attempts,
supporting rollback functionality and historical analysis.
"""

from typing import List, Optional
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models import CalibrationHistoryModel


def create_calibration_record(
    db: Session,
    record_id: str,
    sensor_id: str,
    reference_sensor_id: str,
    fitness: float,
    rmse: float,
    quality: str,
    stages_used: List[str],
    pose_before: dict,
    pose_after: dict,
    transformation_matrix: List[List[float]],
    accepted: bool = False,
    notes: str = ""
) -> CalibrationHistoryModel:
    """
    Create a new calibration history record.
    
    Args:
        db: SQLAlchemy session
        record_id: Unique record identifier
        sensor_id: ID of the sensor being calibrated
        reference_sensor_id: ID of the reference sensor
        fitness: Registration fitness score (0-1)
        rmse: Root mean squared error in meters
        quality: Quality classification ("excellent", "good", "poor")
        stages_used: List of stages used (["global", "icp"])
        pose_before: Previous pose dict {x, y, z, roll, pitch, yaw}
        pose_after: New calibrated pose dict
        transformation_matrix: 4x4 transformation matrix
        accepted: Whether user accepted the calibration
        notes: Optional user notes
        
    Returns:
        Created CalibrationHistoryModel instance
    """
    record = CalibrationHistoryModel(
        id=record_id,
        sensor_id=sensor_id,
        reference_sensor_id=reference_sensor_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        fitness=fitness,
        rmse=rmse,
        quality=quality,
        stages_used_json=json.dumps(stages_used),
        pose_before_json=json.dumps(pose_before),
        pose_after_json=json.dumps(pose_after),
        transformation_matrix_json=json.dumps(transformation_matrix),
        accepted=accepted,
        notes=notes
    )
    
    db.add(record)
    db.commit()
    db.refresh(record)
    
    return record


def get_calibration_history(
    db: Session,
    sensor_id: str,
    limit: Optional[int] = None,
    accepted_only: bool = False
) -> List[CalibrationHistoryModel]:
    """
    Retrieve calibration history for a sensor.
    
    Args:
        db: SQLAlchemy session
        sensor_id: ID of the sensor to query
        limit: Maximum number of records to return (None = all)
        accepted_only: If True, only return accepted calibrations
        
    Returns:
        List of CalibrationHistoryModel instances, sorted by timestamp descending
    """
    query = db.query(CalibrationHistoryModel).filter(
        CalibrationHistoryModel.sensor_id == sensor_id
    )
    
    if accepted_only:
        query = query.filter(CalibrationHistoryModel.accepted == True)
    
    query = query.order_by(desc(CalibrationHistoryModel.timestamp))
    
    if limit is not None:
        query = query.limit(limit)
    
    return query.all()


def get_calibration_by_id(db: Session, record_id: str) -> Optional[CalibrationHistoryModel]:
    """
    Retrieve a specific calibration record by ID.
    
    Args:
        db: SQLAlchemy session
        record_id: Unique record identifier
        
    Returns:
        CalibrationHistoryModel instance or None if not found
    """
    return db.query(CalibrationHistoryModel).filter(
        CalibrationHistoryModel.id == record_id
    ).first()


def get_calibration_by_timestamp(
    db: Session,
    sensor_id: str,
    timestamp: str
) -> Optional[CalibrationHistoryModel]:
    """
    Retrieve a calibration record by sensor ID and timestamp.
    
    Args:
        db: SQLAlchemy session
        sensor_id: ID of the sensor
        timestamp: ISO format timestamp string
        
    Returns:
        CalibrationHistoryModel instance or None if not found
    """
    return db.query(CalibrationHistoryModel).filter(
        CalibrationHistoryModel.sensor_id == sensor_id,
        CalibrationHistoryModel.timestamp == timestamp
    ).first()


def get_latest_accepted_calibration(
    db: Session,
    sensor_id: str
) -> Optional[CalibrationHistoryModel]:
    """
    Retrieve the most recent accepted calibration for a sensor.
    
    Args:
        db: SQLAlchemy session
        sensor_id: ID of the sensor
        
    Returns:
        CalibrationHistoryModel instance or None if no accepted calibrations exist
    """
    return db.query(CalibrationHistoryModel).filter(
        CalibrationHistoryModel.sensor_id == sensor_id,
        CalibrationHistoryModel.accepted == True
    ).order_by(desc(CalibrationHistoryModel.timestamp)).first()


def update_calibration_acceptance(
    db: Session,
    record_id: str,
    accepted: bool,
    notes: Optional[str] = None
) -> Optional[CalibrationHistoryModel]:
    """
    Update the acceptance status of a calibration record.
    
    Args:
        db: SQLAlchemy session
        record_id: Unique record identifier
        accepted: New acceptance status
        notes: Optional updated notes
        
    Returns:
        Updated CalibrationHistoryModel instance or None if not found
    """
    record = get_calibration_by_id(db, record_id)
    
    if record is None:
        return None
    
    record.accepted = accepted
    if notes is not None:
        record.notes = notes
    
    db.commit()
    db.refresh(record)
    
    return record


def delete_calibration(db: Session, record_id: str) -> bool:
    """
    Delete a calibration record.
    
    Args:
        db: SQLAlchemy session
        record_id: Unique record identifier
        
    Returns:
        True if deleted, False if not found
    """
    record = get_calibration_by_id(db, record_id)
    
    if record is None:
        return False
    
    db.delete(record)
    db.commit()
    
    return True


def get_calibration_statistics(db: Session, sensor_id: str) -> dict:
    """
    Get statistical summary of calibration attempts for a sensor.
    
    Args:
        db: SQLAlchemy session
        sensor_id: ID of the sensor
        
    Returns:
        Dict with statistics: total_attempts, accepted_count, avg_fitness, avg_rmse
    """
    records = get_calibration_history(db, sensor_id)
    
    if not records:
        return {
            "total_attempts": 0,
            "accepted_count": 0,
            "avg_fitness": 0.0,
            "avg_rmse": 0.0
        }
    
    accepted_records = [r for r in records if r.accepted]
    
    return {
        "total_attempts": len(records),
        "accepted_count": len(accepted_records),
        "avg_fitness": sum(r.fitness for r in records) / len(records),
        "avg_rmse": sum(r.rmse for r in records) / len(records),
        "best_fitness": max(r.fitness for r in records),
        "best_rmse": min(r.rmse for r in records)
    }
