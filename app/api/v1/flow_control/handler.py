"""
Flow control API router configuration and endpoint definitions.
"""
from fastapi import APIRouter

from .dto import ExternalStateResponse, SnapshotTriggerResponse
from .service import set_external_state, reset_external_state, trigger_snapshot


# Router configuration
router = APIRouter(tags=["Flow Control"])


# Endpoint configurations

@router.post(
    "/nodes/{node_id}/flow-control/set",
    response_model=ExternalStateResponse,
    responses={
        404: {"description": "Node not found or wrong type"},
    },
    summary="Set External State",
    description="Set external_state to True for conditional routing in IF nodes"
)
async def set_external_state_endpoint(node_id: str):
    """
    Set the external_state to True for an IF condition node.

    This allows external applications to enable data flow through conditional
    routing nodes via REST API without modifying the DAG configuration.
    No request body is needed — calling this endpoint always sets the state to True.
    """
    return await set_external_state(node_id)


@router.post(
    "/nodes/{node_id}/flow-control/reset",
    response_model=ExternalStateResponse,
    responses={
        404: {"description": "Node not found or wrong type"}
    },
    summary="Reset External State",
    description="Reset external_state to False for an IF condition node"
)
async def reset_external_state_endpoint(node_id: str):
    """
    Reset the external_state to False for an IF condition node.

    No request body is needed — calling this endpoint always sets the state to False.
    """
    return await reset_external_state(node_id)


@router.post(
    "/nodes/{node_id}/trigger",
    response_model=SnapshotTriggerResponse,
    responses={
        400: {"description": "Node exists but is not a snapshot node"},
        404: {"description": "Node not found or no upstream data available yet"},
        409: {"description": "Trigger dropped: prior snapshot still processing"},
        429: {"description": "Trigger dropped: throttle window active"},
        500: {"description": "Internal processing error during forwarding"},
    },
    summary="Trigger Snapshot",
    description="Capture the latest upstream point cloud held by a Snapshot Node and forward it downstream.",
)
async def trigger_snapshot_endpoint(node_id: str):
    """
    Trigger the named SnapshotNode to capture and forward its cached payload.

    Returns ``{"status": "ok"}`` on success.  Error responses follow the
    FastAPI default ``{"detail": "…"}`` shape.
    """
    return await trigger_snapshot(node_id)

