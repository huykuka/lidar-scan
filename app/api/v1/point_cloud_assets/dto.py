"""Point cloud assets DTOs."""

from typing import List

from pydantic import BaseModel, Field


class PointCloudAsset(BaseModel):
    id: str
    name: str
    filename: str
    format: str
    point_count: int
    size_bytes: int
    bbox_min: List[float]
    bbox_max: List[float]
    extent: List[float] = Field(..., description="Bounding-box size [x, y, z] in the file's units")
    created_at: float = Field(..., description="Unix timestamp (seconds)")


class PointCloudAssetList(BaseModel):
    assets: List[PointCloudAsset]
    count: int


class PointCloudPreview(BaseModel):
    id: str
    total_points: int
    returned_points: int
    points: List[List[float]]


class RenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
