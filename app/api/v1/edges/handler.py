"""Edges router — read-only endpoint.

Note: POST /edges (create), DELETE /edges/{edge_id} (delete), and
POST /edges/bulk (bulk-save) have been removed. All DAG topology changes are
now performed atomically via PUT /api/v1/dag/config. This router retains only
the read-only GET /edges endpoint used for status inspection.
"""

from fastapi import APIRouter
from app.api.v1.schemas.edges import EdgeRecord
from .service import list_edges


# Router configuration
router = APIRouter(tags=["Edges"])


@router.get(
    "/edges",
    response_model=list[EdgeRecord],
    summary="List Edges",
    description="List all current DAG edges. Use PUT /dag/config to modify edges.",
)
async def edges_list_endpoint():
    return await list_edges()
