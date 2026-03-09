"""System-related schema models for pipeline control and status."""

from typing import List
from pydantic import BaseModel


class SystemStatusResponse(BaseModel):
    """System status and health information."""
    is_running: bool
    active_sensors: List[str]
    version: str


class SystemControlResponse(BaseModel):
    """Response for system start/stop control operations."""
    status: str
    is_running: bool