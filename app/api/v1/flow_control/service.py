"""
Flow control API service layer.

Business logic for external state control of IF condition nodes
and snapshot trigger operations.
"""
import time
from fastapi import HTTPException

from app.services.nodes.instance import node_manager
from app.modules.flow_control.if_condition.node import IfConditionNode
from .dto import ExternalStateResponse, SnapshotTriggerResponse


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


async def trigger_snapshot(node_id: str) -> SnapshotTriggerResponse:
    """
    Trigger a snapshot on the specified SnapshotNode.

    Looks up ``node_id`` in the active NodeManager, validates the type,
    then delegates guard logic and forwarding to ``SnapshotNode.trigger_snapshot()``.

    Args:
        node_id: Unique identifier of the target SnapshotNode.

    Returns:
        SnapshotTriggerResponse with ``status="ok"``.

    Raises:
        HTTPException(404): Node not found.
        HTTPException(400): Node exists but is not a SnapshotNode.
        HTTPException(404/409/429/500): Propagated from SnapshotNode.trigger_snapshot().
    """
    # Lazy import avoids circular dependency during module initialisation.
    from app.modules.flow_control.snapshot.node import SnapshotNode  # noqa: PLC0415

    node = node_manager.nodes.get(node_id)

    if node is None:
        raise HTTPException(
            status_code=404,
            detail=f"Node {node_id!r} not found",
        )

    if not isinstance(node, SnapshotNode):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id!r} is not a snapshot node (type: {type(node).__name__})",
        )

    # Delegate — SnapshotNode.trigger_snapshot() raises 404/409/429/500 as needed.
    await node.trigger_snapshot()
    return SnapshotTriggerResponse(status="ok")
