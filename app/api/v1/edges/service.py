"""Edges endpoint handlers - Pure business logic without routing configuration.

Note: create_edge, delete_edge, save_edges_bulk, and EdgeCreateUpdate have been
removed. All DAG mutation (add/update/delete nodes & edges) is now performed
exclusively via PUT /api/v1/dag/config (atomic full-replace). This file retains
only the read-only list_edges helper used by GET /edges.
"""

from app.repositories import EdgeRepository


async def list_edges():
    """List all DAG edges."""
    repo = EdgeRepository()
    return repo.list()
