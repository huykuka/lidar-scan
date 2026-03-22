"""Calibration DTOs - Data Transfer Objects for request/response serialization."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class TriggerCalibrationRequest(BaseModel):
    """Request body for triggering calibration."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "reference_sensor_id": "sensor-uuid-ref",
                    "source_sensor_ids": ["sensor-uuid-a", "sensor-uuid-b"], 
                    "sample_frames": 5
                }
            ]
        }
    )
    
    reference_sensor_id: Optional[str] = None
    source_sensor_ids: Optional[List[str]] = None
    sample_frames: int = 5


class AcceptCalibrationRequest(BaseModel):
    """Request body for accepting calibration."""
    sensor_ids: Optional[List[str]] = None  # None = all pending


class RollbackRequest(BaseModel):
    """Request body for rollback operation."""
    record_id: str