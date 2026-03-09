"""WebSocket DTOs - Data Transfer Objects for request/response serialization."""

from typing import List, Dict
from pydantic import BaseModel


class TopicsResponse(BaseModel):
    """Response for listing available WebSocket topics."""
    topics: List[str]
    description: Dict[str, str]