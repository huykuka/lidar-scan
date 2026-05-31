"""Nodes router configuration and endpoint metadata.

Note: POST /nodes (create/update) and DELETE /nodes/{node_id} have been removed.
All node creation, update, and deletion is now performed atomically via
PUT /api/v1/dag/config. This router retains read-only and live-action endpoints.
"""

from fastapi import APIRouter, Depends

from app.api.v1.auth.dependencies import require_admin, require_service
from app.api.v1.auth.service import UserInfo
from app.services.nodes.schema import NodeDefinition
from app.api.v1.schemas.nodes import (
    NodeRecord,
    NodesStatusResponse,
    NodeReloadResponse,
    ReloadStatusResponse,
)
from app.api.v1.schemas.common import StatusResponse
from .service import (
    list_nodes, list_node_definitions, get_node,
    set_node_enabled, set_node_visible, reload_all_config, get_nodes_status,
    reload_single_node, get_reload_status,
    list_node_type_registry, set_node_type_enabled,
    NodeStatusToggle, NodeVisibilityToggle, NodeTypeToggle, NodeTypeRecord,
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
    "/nodes/definitions/registry",
    response_model=list[NodeTypeRecord],
    summary="List Node Type Registry",
    description=(
        "Returns every scanned node definition with its enabled/disabled state. "
        "Disabled types are hidden from the palette but remain on disk."
    ),
)
async def nodes_definitions_registry_endpoint(
    _service: UserInfo = Depends(require_service),
):
    return await list_node_type_registry()


@router.put(
    "/nodes/definitions/{node_type}/enabled",
    summary="Enable / Disable a Node Type",
    description=(
        "Toggle a node type on or off. Disabling a type hides it from the "
        "palette and disables all existing DAG instances of that type."
    ),
    responses={404: {"description": "Node type not found"}},
)
async def nodes_definition_toggle_endpoint(
    node_type: str,
    req: NodeTypeToggle,
    _service: UserInfo = Depends(require_service),
):
    return await set_node_type_enabled(node_type, req)


@router.get(
    "/nodes/reload/status",
    response_model=ReloadStatusResponse,
    summary="Get Reload Status",
    description="Returns the current state of the reload lock and any in-progress selective reload.",
)
async def nodes_reload_status_endpoint():
    return await get_reload_status()


@router.post(
    "/nodes/reload",
    response_model=StatusResponse,
    responses={409: {"description": "Reload in progress"}},
    summary="Reload Configuration",
    description="Reload all node configurations from database.",
)
async def nodes_reload_endpoint(
    _admin: UserInfo = Depends(require_admin),
):
    return await reload_all_config()


@router.post(
    "/nodes/{node_id}/reload",
    response_model=NodeReloadResponse,
    responses={
        404: {"description": "Node not found in running DAG"},
        409: {"description": "A reload is already in progress"},
        500: {"description": "Reload failed"},
    },
    summary="Selective Node Reload",
    description="Reload a single node's runtime in-place without affecting other nodes or WebSocket connections.",
)
async def node_reload_endpoint(
    node_id: str,
    _admin: UserInfo = Depends(require_admin),
):
    return await reload_single_node(node_id)


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
async def node_visible_endpoint(
    node_id: str,
    req: NodeVisibilityToggle,
    _admin: UserInfo = Depends(require_admin),
):
    return await set_node_visible(node_id, req)


@router.put(
    "/nodes/{node_id}/enabled",
    response_model=StatusResponse,
    summary="Set Node Enabled",
    description="Toggle node enabled state.",
)
async def node_enabled_endpoint(
    node_id: str,
    req: NodeStatusToggle,
    _admin: UserInfo = Depends(require_admin),
):
    return await set_node_enabled(node_id, req)


@router.get(
    "/nodes/status/all",
    response_model=NodesStatusResponse,
    summary="Get Nodes Status",
    description="Returns runtime status of all nodes based on their engine handlers",
)
async def nodes_status_endpoint():
    return await get_nodes_status()
