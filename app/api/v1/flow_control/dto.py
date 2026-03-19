"""
Pydantic models for flow control API endpoints.
"""
from pydantic import BaseModel, Field


class SetExternalStateRequest(BaseModel):
    """Request body for setting external state."""
    model_config = {"strict": True}
    value: bool = Field(..., description="Boolean state value (true or false)")


class ExternalStateResponse(BaseModel):
    """Response for external state operations."""
    node_id: str = Field(..., description="Node identifier")
    state: bool = Field(..., description="Current external state value")
    timestamp: float = Field(..., description="Unix timestamp of the state change")
