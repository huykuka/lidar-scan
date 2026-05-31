"""Admin router — node type management endpoints."""

from fastapi import APIRouter

from .service import (
    NodeTypeRecord,
    NodeTypeToggle,
    list_node_types,
    set_node_type_enabled,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/node-types",
    response_model=list[NodeTypeRecord],
    summary="List All Node Types",
    description=(
        "Returns every scanned node definition with its enabled/disabled state. "
        "Disabled types are hidden from the palette but remain on disk."
    ),
)
async def admin_list_node_types():
    return await list_node_types()


@router.put(
    "/node-types/{node_type}/enabled",
    summary="Enable / Disable a Node Type",
    description=(
        "Toggle a node type on or off. Disabling a type hides it from the "
        "palette and disables all existing DAG instances of that type."
    ),
    responses={404: {"description": "Node type not found"}},
)
async def admin_toggle_node_type(node_type: str, req: NodeTypeToggle):
    return await set_node_type_enabled(node_type, req)
