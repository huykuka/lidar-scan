"""Calibration-related schema models for ICP multi-sensor calibration."""

from typing import Dict, List, Optional
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


class RollbackResponse(BaseModel):
    """Response for calibration rollback operations."""
    success: bool
    sensor_id: str
    restored_to: str  # ISO-8601 timestamp


class CalibrationRecord(BaseModel):
    """Historical calibration record."""
    id: str
    sensor_id: str
    timestamp: str
    accepted: bool
    fitness: Optional[float] = None
    rmse: Optional[float] = None
    source_sensor_id: Optional[str] = None  # Leaf sensor ID for provenance tracking
    processing_chain: List[str] = []  # DAG path from leaf sensor to calibration node
    run_id: Optional[str] = None  # UUID for multi-sensor run correlation


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