"""Assets DTOs - Data Transfer Objects for request/response serialization."""

from typing import List
from pydantic import BaseModel


class ThumbnailItem(BaseModel):
    """Individual thumbnail file information."""
    filename: str
    url: str
    size: int


class ThumbnailListResponse(BaseModel):
    """Response for listing thumbnail files."""
    thumbnails: List[ThumbnailItem]
    count: int
    assets_dir: str