"""
Flow control API router configuration and endpoint definitions.
"""
from fastapi import APIRouter

from .dto import ExternalStateResponse
from .service import set_external_state, reset_external_state


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
