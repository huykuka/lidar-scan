"""PCD Injection DTOs — request/response models for multipart PCD upload."""

from pydantic import BaseModel, Field


class PcdInjectionResponse(BaseModel):
    """Response returned after a successful PCD injection."""
    node_id: str = Field(..., description="ID of the PCD Injection node that received the data")
    points_injected: int = Field(..., description="Number of 3D points parsed and forwarded into the DAG")
    message: str = Field(default="ok", description="Human-readable status message")
