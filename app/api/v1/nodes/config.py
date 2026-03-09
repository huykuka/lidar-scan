"""Nodes router configuration and endpoint metadata."""

from fastapi import APIRouter
from app.services.nodes.schema import NodeDefinition
from app.api.v1.schemas.nodes import NodeRecord, NodesStatusResponse
from app.api.v1.schemas.common import StatusResponse, UpsertResponse
from .handlers import (
    list_nodes, list_node_definitions, get_node, upsert_node,
    set_node_enabled, delete_node, reload_all_config, get_nodes_status,
    NodeCreateUpdate, NodeStatusToggle
)


# Router configuration
router = APIRouter(tags=["Nodes"])

# Endpoint configurations
@router.get(
    "/nodes",
    response_model=list[NodeRecord],
    summary="List Nodes",
    description="List all configured nodes in the system.",
)
async def nodes_list_endpoint():
    return await list_nodes()


@router.get(
    "/nodes/definitions", 
    response_model=list[NodeDefinition],
    summary="List Node Definitions",
    description="Returns all available node types and their configuration schemas",
)
async def nodes_definitions_endpoint():
    return await list_node_definitions()


@router.get(
    "/nodes/{node_id}",
    response_model=NodeRecord,
    responses={404: {"description": "Node not found"}},
    summary="Get Node",
    description="Get a single node configuration by ID.",
)
async def node_get_endpoint(node_id: str):
    return await get_node(node_id)


@router.post(
    "/nodes",
    response_model=UpsertResponse,
    summary="Create/Update Node",
    description="Create a new node or update an existing one.",
)
async def node_upsert_endpoint(req: NodeCreateUpdate):
    return await upsert_node(req)


@router.put(
    "/nodes/{node_id}/enabled",
    response_model=StatusResponse,
    summary="Set Node Enabled",
    description="Toggle node enabled state.",
)
async def node_enabled_endpoint(node_id: str, req: NodeStatusToggle):
    return await set_node_enabled(node_id, req)


@router.delete(
    "/nodes/{node_id}",
    response_model=StatusResponse,
    responses={404: {"description": "Node not found"}},
    summary="Delete Node",
    description="Delete a node and all associated edges.",
)
async def node_delete_endpoint(node_id: str):
    return await delete_node(node_id)


@router.post(
    "/nodes/reload",
    response_model=StatusResponse,
    responses={409: {"description": "Reload in progress"}},
    summary="Reload Configuration",
    description="Reload all node configurations from database.",
)
async def nodes_reload_endpoint():
    return await reload_all_config()


@router.get(
    "/nodes/status/all",
    response_model=NodesStatusResponse,
    summary="Get Nodes Status",
    description="Returns runtime status of all nodes based on their engine handlers",
)
async def nodes_status_endpoint():
    return await get_nodes_status()