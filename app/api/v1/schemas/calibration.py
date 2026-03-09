"""Calibration-related schema models for ICP multi-sensor calibration."""

from typing import Dict, List, Optional
from pydantic import BaseModel


class CalibrationResult(BaseModel):
    """Per-sensor ICP calibration result."""
    fitness: Optional[float] = None
    rmse: Optional[float] = None
    quality: Optional[str] = None  # "good" | "acceptable" | "poor"


class CalibrationTriggerResponse(BaseModel):
    """Response for calibration trigger operations."""
    success: bool
    results: Dict[str, CalibrationResult]
    pending_approval: bool


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