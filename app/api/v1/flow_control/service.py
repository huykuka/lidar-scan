"""
Flow control API service layer.

Business logic for external state control of IF condition nodes.
"""
import time
from fastapi import HTTPException

from app.services.nodes.instance import node_manager
from app.modules.flow_control.if_condition.node import IfConditionNode
from .dto import ExternalStateResponse


async def set_external_state(node_id: str) -> ExternalStateResponse:
    """
    Set external_state to True for a specific IF condition node.

    Args:
        node_id: Node identifier

    Returns:
        ExternalStateResponse with updated state

    Raises:
        HTTPException: 404 if node not found or not an IF condition node
    """
    node = node_manager.nodes.get(node_id)

    if not node or not isinstance(node, IfConditionNode):
        raise HTTPException(
            status_code=404,
            detail="Node not found or not a flow control node"
        )

    node.external_state = True
    node.state = True  # Immediately set state

    return ExternalStateResponse(
        node_id=node_id,
        state=True,
        timestamp=time.time()
    )


async def reset_external_state(node_id: str) -> ExternalStateResponse:
    """
    Reset external_state to False for a specific IF condition node.

    Args:
        node_id: Node identifier

    Returns:
        ExternalStateResponse with state set to False

    Raises:
        HTTPException: 404 if node not found or not an IF condition node
    """
    node = node_manager.nodes.get(node_id)

    if not node or not isinstance(node, IfConditionNode):
        raise HTTPException(
            status_code=404,
            detail="Node not found or not a flow control node"
        )

    node.external_state = None  # Disable external control
    node.state = None  # Clear state (will use expression on next input)

    return ExternalStateResponse(
        node_id=node_id,
        state=False,
        timestamp=time.time()
    )
