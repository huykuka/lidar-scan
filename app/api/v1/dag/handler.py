"""FastAPI router for DAG config endpoints.

Endpoints:
    GET  /dag/config  — fetch full DAG (nodes + edges) + current config_version
    PUT  /dag/config  — atomic save: replace DAG + trigger reload
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.schemas.dag import (
    DagConfigResponse,
    DagConfigSaveRequest,
    DagConfigSaveResponse,
)
from .service import get_dag_config, save_dag_config

router = APIRouter(tags=["DAG"])


@router.get(
    "/dag/config",
    response_model=DagConfigResponse,
    summary="Get DAG Configuration",
    description=(
        "Returns all nodes, edges, and current config_version for optimistic locking. "
        "Used by the frontend on initial load and after a Sync action."
    ),
    tags=["DAG"],
)
async def dag_config_get_endpoint() -> DagConfigResponse:
    return await get_dag_config()


@router.put(
    "/dag/config",
    response_model=DagConfigSaveResponse,
    responses={
        409: {"description": "Version conflict or reload in progress"},
        422: {"description": "Invalid DAG configuration"},
        500: {"description": "Save or reload failure"},
    },
    summary="Save DAG Configuration",
    description=(
        "Atomically replaces all nodes and edges, increments config_version, "
        "and triggers a DAG reload. Rejects with 409 if base_version is stale."
    ),
    tags=["DAG"],
)
async def dag_config_save_endpoint(req: DagConfigSaveRequest) -> DagConfigSaveResponse:
    return await save_dag_config(req)
