"""Detection DTOs — Data Transfer Objects for request/response serialization."""

from typing import List, Optional

from pydantic import BaseModel


class ModelInfo(BaseModel):
    """Metadata for a single uploaded model checkpoint."""

    id: str
    filename: str
    display_name: str
    model_type: str
    file_size: int
    uploaded_at: float
    description: str
    path: str


class ModelListResponse(BaseModel):
    """Response for listing uploaded detection models."""

    models: List[ModelInfo]
    count: int


class ModelUploadResponse(BaseModel):
    """Response after a successful model upload."""

    model: ModelInfo
    message: str


class ModelDeleteResponse(BaseModel):
    """Response after deleting a model."""

    deleted: bool
    message: str
