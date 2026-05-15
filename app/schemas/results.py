"""
Pydantic V2 schemas for Application Node Results Storage.

Spec: .opencode/plans/application-results-storage/api-spec.md
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Color domain mapping for PCD labels
# ---------------------------------------------------------------------------

#: Canonical hex color assigned to each well-known PCD label.
#: Falls back to ``PCD_COLOR_DEFAULT`` for unknown labels.
PCD_LABEL_COLORS: Dict[str, str] = {
    "empty": "#2196F3",  # blue
    "loaded": "#F44336",  # red
    "merged": "#4CAF50",  # green
}

#: Default color for labels not present in ``PCD_LABEL_COLORS``.
PCD_COLOR_DEFAULT: str = "#9E9E9E"  # grey


def pcd_color_for_label(label: str) -> str:
    """Return the canonical hex color for a PCD label (case-insensitive match).

    Args:
        label: Sanitized PCD label string (e.g. ``"empty"``, ``"loaded"``).

    Returns:
        Hex color string such as ``"#2196F3"``.
    """
    return PCD_LABEL_COLORS.get(label.lower(), PCD_COLOR_DEFAULT)


class PcdFileEntry(BaseModel):
    """A single PCD file associated with a result.

    ``path`` is relative to the static ``/data/`` mount, e.g.
    ``results/<node_id>/<result_id>/<label>.pcd``.

    Frontend constructs the full URL as:  ``/data/${path}``

    The backend NEVER emits absolute URLs or proxy/download endpoints for
    result PCD files.  Files are served directly by the static-file mount.

    ``color`` is a hex string (e.g. ``"#2196F3"``) derived from the PCD label
    via ``pcd_color_for_label()``.  Canonical mapping: empty=blue, loaded=red,
    merged=green; unknown labels receive the default grey ``"#9E9E9E"``.
    """

    label: str
    path: str  # relative to /data/, e.g. "results/<node_id>/<result_id>/<label>.pcd"
    color: str  # hex color derived from label, e.g. "#2196F3"


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
