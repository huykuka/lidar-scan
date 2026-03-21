"""Nodes router configuration and endpoint metadata.

Note: POST /nodes (create/update) and DELETE /nodes/{node_id} have been removed.
All node creation, update, and deletion is now performed atomically via
PUT /api/v1/dag/config. This router retains read-only and live-action endpoints.
"""

from fastapi import APIRouter
from app.services.nodes.schema import NodeDefinition
from app.api.v1.schemas.nodes import NodeRecord, NodesStatusResponse
from app.api.v1.schemas.common import StatusResponse
from .service import (
    list_nodes, list_node_definitions, get_node,
    set_node_enabled, set_node_visible, reload_all_config, get_nodes_status,
    NodeStatusToggle, NodeVisibilityToggle
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


@router.put(
    "/nodes/{node_id}/visible",
    response_model=StatusResponse,
    responses={
        400: {"description": "Cannot change visibility of system topic"},
        404: {"description": "Node not found"}
    },
    summary="Set Node Visible",
    description="Toggle node visibility state. Controls whether the node streams data to WebSocket.",
)
async def node_visible_endpoint(node_id: str, req: NodeVisibilityToggle):
    return await set_node_visible(node_id, req)


@router.put(
    "/nodes/{node_id}/enabled",
    response_model=StatusResponse,
    summary="Set Node Enabled",
    description="Toggle node enabled state.",
)
async def node_enabled_endpoint(node_id: str, req: NodeStatusToggle):
    return await set_node_enabled(node_id, req)


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
