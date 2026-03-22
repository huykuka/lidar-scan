"""Calibration-related schema models for ICP multi-sensor calibration."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class CalibrationResult(BaseModel):
    """Per-sensor ICP calibration result."""
    fitness: Optional[float] = None
    rmse: Optional[float] = None
    quality: Optional[str] = None  # "good" | "acceptable" | "poor"
    source_sensor_id: Optional[str] = None  # Leaf sensor ID (lidar_id)
    processing_chain: List[str] = []  # DAG path from leaf sensor to calibration node


class CalibrationTriggerResponse(BaseModel):
    """Response for calibration trigger operations."""
    success: bool
    results: Dict[str, CalibrationResult]
    pending_approval: bool
    run_id: Optional[str] = None  # UUID correlating multi-sensor calibration runs


class AcceptResponse(BaseModel):
    """Response for calibration acceptance operations."""
    success: bool
    accepted: List[str]


class RejectResponse(BaseModel):
    """Response for calibration rejection operations."""
    success: bool
    rejected: List[str]  # leaf sensor IDs whose pending results were discarded


class RollbackResponse(BaseModel):
    """Response for calibration rollback operations."""
    success: bool
    sensor_id: str
    restored_to: str  # ISO-8601 timestamp
    new_record_id: str  # ID of the newly created rollback history record


class PendingCalibrationResult(BaseModel):
    """Per-sensor pending calibration result for status polling."""
    fitness: float
    rmse: float
    quality: str
    quality_good: bool
    source_sensor_id: Optional[str] = None
    processing_chain: List[str] = []
    pose_before: Dict[str, float]
    pose_after: Dict[str, float]
    transformation_matrix: List[List[float]]


class CalibrationNodeStatusResponse(BaseModel):
    """Response from GET /calibration/{node_id}/status polling endpoint."""
    node_id: str
    node_name: str
    enabled: bool
    calibration_state: str          # "idle" | "pending"
    quality_good: Optional[bool]    # None if no pending; True if all results above threshold
    reference_sensor_id: Optional[str]
    source_sensor_ids: List[str]
    buffered_frames: Dict[str, int]  # {sensor_id: frame_count}
    last_calibration_time: Optional[str]
    pending_results: Dict[str, PendingCalibrationResult]


class CalibrationRecord(BaseModel):
    """Historical calibration record."""
    id: str
    sensor_id: str
    timestamp: str
    accepted: bool
    # New fields — all Optional for backward compatibility with legacy records
    reference_sensor_id: Optional[str] = None
    accepted_at: Optional[str] = None
    accepted_by: Optional[str] = None
    fitness: Optional[float] = None
    rmse: Optional[float] = None
    quality: Optional[str] = None
    stages_used: List[str] = []
    pose_before: Optional[Dict[str, float]] = None
    pose_after: Optional[Dict[str, float]] = None
    transformation_matrix: Optional[List[List[float]]] = None
    source_sensor_id: Optional[str] = None
    processing_chain: List[str] = []
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    rollback_source_id: Optional[str] = None
    registration_method: Optional[Dict[str, Any]] = None
    notes: str = ""


class CalibrationHistoryResponse(BaseModel):
    """Response containing calibration history for a sensor."""
    sensor_id: str
    history: List[CalibrationRecord]


class CalibrationStatsResponse(BaseModel):
    """Response containing calibration statistics for a sensor."""
    sensor_id: str
    total_attempts: int
    accepted_count: int
    avg_fitness: Optional[float] = None
    avg_rmse: Optional[float] = None