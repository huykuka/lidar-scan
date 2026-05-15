"""
Results API router — GET/DELETE endpoints for application node results.

Spec: .opencode/plans/application-results-storage/api-spec.md
Mounted at: /api/v1/results
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.results import (
    DeleteResultResponse,
    NodeResultSummary,
    ResultDetail,
    ResultSummary,
)
from app.services.results_storage import ResultsStorageService

# Lazy singleton — initialised on first import of this module.
# Tests may monkey-patch this attribute directly for isolation.
_results_service: Optional[ResultsStorageService] = None


def _get_service() -> ResultsStorageService:
    global _results_service
    if _results_service is None:
        _results_service = ResultsStorageService()
    return _results_service


router = APIRouter(tags=["Results"])


# ---------------------------------------------------------------------------
# GET /results — node index (all application nodes merged with DAG state)
# ---------------------------------------------------------------------------


@router.get(
    "/results",
    response_model=List[NodeResultSummary],
    summary="List application nodes with results",
    description=(
        "Returns all application nodes that have ≥1 stored result, merged with "
        "active DAG nodes of category 'application'. Nodes with zero results are "
        "included if they are currently active in the DAG."
    ),
)
async def list_node_results_index() -> List[NodeResultSummary]:
    """Merge DB result counts with live DAG application node metadata."""
    svc = _get_service()
    try:
        db_summaries = await svc.get_node_index()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Storage error: {exc}") from exc

    # Build a map from DB data
    db_map: dict[str, NodeResultSummary] = {s.node_id: s for s in db_summaries}

    # Merge with active DAG application nodes
    try:
        from app.services.nodes.instance import node_manager
        from app.modules.application.registry import (  # noqa: F401 — ensure registries loaded
            environment_filtering_registry,
            vehicle_profiler_registry,
            volume_calculation_registry,
        )

        # Application node types (all nodes registered under the application category)
        _APPLICATION_CATEGORIES = {"application"}

        merged: List[NodeResultSummary] = []
        seen_node_ids: set[str] = set()

        for node_id, node_instance in node_manager.nodes.items():
            # Find the node_data for category lookup
            node_data = next(
                (n for n in node_manager.nodes_data if n.get("id") == node_id), None
            )
            if node_data is None:
                continue
            category = node_data.get("category", "")
            if category != "application":
                continue

            seen_node_ids.add(node_id)
            db_entry = db_map.get(node_id)
            merged.append(
                NodeResultSummary(
                    node_id=node_id,
                    node_name=getattr(node_instance, "name", node_id),
                    node_type=node_data.get("type", "unknown"),
                    result_count=db_entry.result_count if db_entry else 0,
                    latest_timestamp=db_entry.latest_timestamp if db_entry else None,
                )
            )

        # Also include nodes that have results in DB but are no longer in DAG
        for node_id, db_entry in db_map.items():
            if node_id not in seen_node_ids:
                merged.append(
                    NodeResultSummary(
                        node_id=node_id,
                        node_name=node_id,
                        node_type="unknown",
                        result_count=db_entry.result_count,
                        latest_timestamp=db_entry.latest_timestamp,
                    )
                )

        return merged

    except Exception as exc:
        # DAG not available (e.g. tests); fall back to DB-only data
        return [
            NodeResultSummary(
                node_id=s.node_id,
                node_name=s.node_id,
                node_type="unknown",
                result_count=s.result_count,
                latest_timestamp=s.latest_timestamp,
            )
            for s in db_summaries
        ]


# ---------------------------------------------------------------------------
# GET /results/{node_id} — per-node result list
# ---------------------------------------------------------------------------


@router.get(
    "/results/{node_id}",
    response_model=List[ResultSummary],
    responses={404: {"description": "Node not found or has no results"}},
    summary="List results for a node",
    description="Returns all results for the given node, newest first.",
)
async def list_results_by_node(
    node_id: str,
    limit: int = Query(default=100, ge=1, le=1000, description="Max results to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> List[ResultSummary]:
    svc = _get_service()
    try:
        # Check if node exists in DAG or has results in DB
        results = await svc.get_results_by_node(node_id, limit=limit, offset=offset)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Storage error: {exc}") from exc

    if not results:
        # Check if node exists in DAG — if so return empty list; otherwise 404
        try:
            from app.services.nodes.instance import node_manager

            if node_id not in node_manager.nodes:
                # Check if node is in nodes_data (disabled nodes)
                in_data = any(n.get("id") == node_id for n in node_manager.nodes_data)
                if not in_data:
                    raise HTTPException(status_code=404, detail="Node not found")
        except HTTPException:
            raise
        except Exception:
            # DAG unavailable — if no results found return 404
            raise HTTPException(status_code=404, detail="Node not found")

    return results


# ---------------------------------------------------------------------------
# GET /results/{node_id}/{result_id} — result detail
# ---------------------------------------------------------------------------


@router.get(
    "/results/{node_id}/{result_id}",
    response_model=ResultDetail,
    responses={404: {"description": "Result not found"}},
    summary="Get result detail",
    description="Returns full result detail including metadata and PCD file URLs.",
)
async def get_result_detail(node_id: str, result_id: str) -> ResultDetail:
    svc = _get_service()
    try:
        detail = await svc.get_result_detail(node_id, result_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Storage error: {exc}") from exc

    if detail is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return detail


# ---------------------------------------------------------------------------
# DELETE /results/{node_id}/{result_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/results/{node_id}/{result_id}",
    response_model=DeleteResultResponse,
    responses={404: {"description": "Result not found"}},
    summary="Delete a result",
    description="Permanently delete a single result record and its PCD files.",
)
async def delete_result(node_id: str, result_id: str) -> DeleteResultResponse:
    svc = _get_service()
    try:
        deleted = await svc.delete_result(node_id, result_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Storage error: {exc}") from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Result not found")
    return DeleteResultResponse(deleted=True, result_id=result_id)
