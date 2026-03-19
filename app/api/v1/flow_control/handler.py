"""
Flow control API router configuration and endpoint definitions.
"""
from fastapi import APIRouter

from .dto import SetExternalStateRequest, ExternalStateResponse
from .service import set_external_state, reset_external_state


# Router configuration
router = APIRouter(tags=["Flow Control"])


# Endpoint configurations

@router.post(
    "/nodes/{node_id}/flow-control/set",
    response_model=ExternalStateResponse,
    responses={
        404: {"description": "Node not found or wrong type"},
        400: {"description": "Invalid request body"}
    },
    summary="Set External State",
    description="Update external_state boolean for conditional routing in IF nodes"
)
async def set_external_state_endpoint(node_id: str, req: SetExternalStateRequest):
    """
    Set the external_state boolean for an IF condition node.
    
    This allows external applications to control data flow through conditional
    routing nodes via REST API without modifying the DAG configuration.
    """
    return await set_external_state(node_id, req)


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
    
    This is a convenience endpoint equivalent to calling /set with value=False.
    """
    return await reset_external_state(node_id)
