"""Common response schema models used across multiple API endpoints."""

from pydantic import BaseModel


class StatusResponse(BaseModel):
    """Standard status response for simple operations."""
    status: str


class UpsertResponse(BaseModel):
    """Response for create/update operations that return an ID."""
    status: str
    id: str


class DeleteEdgeResponse(BaseModel):
    """Response for edge deletion operations."""
    status: str
    id: str


class ConflictResponse(BaseModel):
    """Response body for 409 Conflict errors."""
    detail: str