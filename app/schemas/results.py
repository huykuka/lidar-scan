"""
Pydantic V2 schemas for Application Node Results Storage.

Spec: .opencode/plans/application-results-storage/api-spec.md
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class PcdFileEntry(BaseModel):
    """A single PCD file associated with a result."""

    label: str
    url: str


class NodeResultSummary(BaseModel):
    """Summary row for the results overview (one entry per application node)."""

    node_id: str
    node_name: str
    node_type: str
    result_count: int
    latest_timestamp: Optional[float]


class ResultSummary(BaseModel):
    """Lightweight summary used in the per-node result list."""

    result_id: str
    node_id: str
    timestamp: float
    status: Literal["success", "warning", "error"]
    metadata_summary: Dict[str, Any]  # scalar top-level fields only
    pcd_count: int


class ResultDetail(BaseModel):
    """Full result detail including all metadata and PCD file references."""

    result_id: str
    node_id: str
    timestamp: float
    status: Literal["success", "warning", "error"]
    metadata: Dict[str, Any]
    pcd_files: List[PcdFileEntry]


class DeleteResultResponse(BaseModel):
    """Response body for DELETE /results/{node_id}/{result_id}."""

    deleted: bool
    result_id: str
