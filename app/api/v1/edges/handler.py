"""Edges router configuration and endpoint metadata."""

from typing import List
from fastapi import APIRouter
from app.api.v1.schemas.edges import EdgeRecord
from app.api.v1.schemas.common import StatusResponse, DeleteEdgeResponse
from .service import list_edges, create_edge, delete_edge, save_edges_bulk, EdgeCreateUpdate


# Router configuration
router = APIRouter(tags=["Edges"])

# Endpoint configurations
@router.get(
    "/edges",
    response_model=list[EdgeRecord],
    summary="List Edges",
    description="List all DAG edges in the system.",
)
async def edges_list_endpoint():
    return await list_edges()


@router.post(
    "/edges",
    response_model=EdgeRecord,
    summary="Create Edge",
    description="Creates a single edge between two nodes.",
)
async def edge_create_endpoint(edge: EdgeCreateUpdate):
    return await create_edge(edge)


@router.delete(
    "/edges/{edge_id}",
    response_model=DeleteEdgeResponse,
    summary="Delete Edge",
    description="Deletes a single edge by id.",
)
async def edge_delete_endpoint(edge_id: str):
    return await delete_edge(edge_id)


@router.post(
    "/edges/bulk",
    response_model=StatusResponse,
    summary="Bulk Save Edges",
    description="Saves the entire graph of edges sent from the front-end canvas",
)
async def edges_bulk_endpoint(edges: List[EdgeCreateUpdate]):
    return await save_edges_bulk(edges)