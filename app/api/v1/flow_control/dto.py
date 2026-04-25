"""
Pydantic models for flow control API endpoints.
"""
from typing import Literal

from pydantic import BaseModel, Field


class ExternalStateResponse(BaseModel):
    """Response for external state operations."""
    node_id: str = Field(..., description="Node identifier")
    state: bool = Field(..., description="Current external state value")
    timestamp: float = Field(..., description="Unix timestamp of the state change")


class SnapshotTriggerResponse(BaseModel):
    """Response for a successful snapshot trigger."""
    status: Literal["ok"]

