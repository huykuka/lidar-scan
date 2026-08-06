"""Nodes router configuration and endpoint metadata.

Note: POST /nodes (create/update) and DELETE /nodes/{node_id} have been removed.
All node creation, update, and deletion is now performed atomically via
PUT /api/v1/dag/config. This router retains read-only and live-action endpoints.
"""

from fastapi import APIRouter, UploadFile, File

from app.api.v1.auth.dependencies import roles_required
from app.api.v1.schemas.common import StatusResponse
from app.api.v1.schemas.nodes import (
    NodeRecord,
    NodesStatusResponse,
    NodeReloadResponse,
    ReloadStatusResponse,
)
from app.services.nodes.schema import NodeDefinition
from .service import (
    list_nodes, list_node_definitions, get_node,
    reload_all_config, get_nodes_status,
    get_reload_status,
    list_node_type_registry, set_node_type_enabled,
    list_plugins, remove_plugin, upload_plugin,
    calibrate_from_floor, FloorCalibrationRequest,
    NodeTypeToggle, NodeTypeRecord, PluginRecord,
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


@router.post(
    "/nodes/{node_id}/calibrate-from-floor",
    responses={
        404: {"description": "Node not found"},
        400: {"description": "Node does not support floor calibration"},
        409: {"description": "No floor plane found, no frame yet, or IMU auto-level enabled"},
    },
    summary="Calibrate Node Pose from Floor Plane",
    description="Segment the ground plane from the latest frame, derive the tilt "
                "correction, apply it to the node pose, and persist. Works for any "
                "pose-bearing source node. Disabled while IMU auto-level is active.",
)
async def node_calibrate_from_floor_endpoint(
    node_id: str, request: FloorCalibrationRequest = FloorCalibrationRequest()
):
    return await calibrate_from_floor(node_id, request)


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
@roles_required("service")
async def nodes_definitions_registry_endpoint():
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
@roles_required("service")
async def nodes_definition_toggle_endpoint(
        node_type: str,
        req: NodeTypeToggle,
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
@roles_required("admin")
async def nodes_reload_endpoint():
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
@roles_required("admin")
async def node_reload_endpoint(
        node_id: str,
):
    return await reload_single_node(node_id)


@router.get(
    "/nodes/status/all",
    response_model=NodesStatusResponse,
    summary="Get Nodes Status",
    description="Returns runtime status of all nodes based on their engine handlers",
)
async def nodes_status_endpoint():
    return await get_nodes_status()


# ── Plugins ──────────────────────────────────────────────────────────────


@router.get(
    "/nodes/plugins",
    response_model=list[PluginRecord],
    summary="List Plugins",
    description="List all installed plugin packages with their registered types and metadata.",
)
async def nodes_plugins_list_endpoint():
    return await list_plugins()


@router.post(
    "/nodes/plugins/upload",
    summary="Upload Plugin",
    description=(
        "Upload a plugin as a `.zip` file. The zip must contain a single top-level "
        "directory with a `registry.py`. The plugin is loaded immediately after install."
    ),
    responses={
        422: {"description": "Invalid zip structure or missing registry.py"},
        500: {"description": "Error during extraction or load"},
    },
)
@roles_required("service")
async def nodes_plugins_upload_endpoint(
    file: UploadFile = File(..., description="Plugin zip archive"),
):
    zip_bytes = await file.read()
    return await upload_plugin(zip_bytes)


@router.delete(
    "/nodes/plugins/{plugin_name}",
    summary="Remove Plugin",
    description=(
        "Unload a plugin and permanently delete its directory from disk. "
        "All running DAG instances of its node types are stopped. "
        "This cannot be undone — re-install by uploading a new zip."
    ),
    responses={
        404: {"description": "Plugin directory not found"},
    },
)
@roles_required("service")
async def nodes_plugins_remove_endpoint(plugin_name: str):
    return await remove_plugin(plugin_name)


# ── Per-node wildcard routes (must come LAST) ─────────────────────────────


@router.get(
    "/nodes/{node_id}",
    response_model=NodeRecord,
    responses={404: {"description": "Node not found"}},
    summary="Get Node",
    description="Get a single node configuration by ID.",
)
async def node_get_endpoint(node_id: str):
    return await get_node(node_id)
