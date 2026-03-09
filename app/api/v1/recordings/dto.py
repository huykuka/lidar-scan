"""Recordings DTOs - Data Transfer Objects for request/response serialization."""

from pydantic import BaseModel, ConfigDict


class StartRecordingRequest(BaseModel):
    """Request body for starting a recording."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "node_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                    "name": "outdoor-test-run-01",
                    "metadata": {
                        "environment": "outdoor",
                        "weather": "clear"
                    }
                }
            ]
        }
    )
    
    node_id: str
    name: str | None = None
    metadata: dict | None = None


class RecordingResponse(BaseModel):
    """Recording information response."""
    id: str
    name: str
    node_id: str
    sensor_id: str | None
    file_path: str
    file_size_bytes: int
    frame_count: int
    duration_seconds: float
    recording_timestamp: str
    metadata: dict
    thumbnail_path: str | None = None
    created_at: str


class ActiveRecordingResponse(BaseModel):
    """Active recording status response."""
    recording_id: str
    node_id: str
    frame_count: int
    duration_seconds: float
    started_at: str
    metadata: dict | None = None
    status: str = "recording"  # "recording" or "stopping"


class ListRecordingsResponse(BaseModel):
    """Response for listing recordings."""
    recordings: list[RecordingResponse]
    active_recordings: list[ActiveRecordingResponse]