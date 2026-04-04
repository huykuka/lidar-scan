"""Nodes endpoint handlers - Pure business logic without routing configuration.

Note: NodeCreateUpdate, upsert_node, and delete_node have been removed.
All node creation, update, and deletion is now performed atomically via
PUT /api/v1/dag/config. This module retains read operations (list, get, status)
and live-action toggles (enabled, visible, reload) which remain as direct
per-node calls.
"""

import time
from typing import Optional
from fastapi import HTTPException
from pydantic import BaseModel

from app.core.logging import get_logger
from app.repositories import NodeRepository
from app.services.nodes.instance import node_manager
from app.services.nodes.schema import node_schema_registry

logger = get_logger(__name__)


class NodeStatusToggle(BaseModel):
    enabled: bool


class NodeVisibilityToggle(BaseModel):
    visible: bool


async def list_nodes():
    """List all configured nodes."""
    repo = NodeRepository()
    return repo.list()


async def list_node_definitions():
    """Returns all available node types and their configuration schemas"""
    return node_schema_registry.get_all()


async def get_node(node_id: str):
    """Get a single node configuration by ID."""
    repo = NodeRepository()
    node = repo.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


async def set_node_enabled(node_id: str, req: NodeStatusToggle):
    """Toggle node enabled state."""
    repo = NodeRepository()
    repo.set_enabled(node_id, req.enabled)
    return {"status": "success"}


async def set_node_visible(node_id: str, req: NodeVisibilityToggle):
    """Toggle node visibility state."""
    from app.services.websocket.manager import SYSTEM_TOPICS
    from app.services.shared.topics import slugify_topic_prefix

    repo = NodeRepository()

    # Fetch node by ID; raise 404 if not found
    node = repo.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Derive topic name and check against SYSTEM_TOPICS
    node_name = node.get("name", node_id)
    topic = f"{slugify_topic_prefix(node_name)}_{node_id[:8]}"

    if topic in SYSTEM_TOPICS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot change visibility of system topic '{topic}'",
        )

    # Update visibility in database
    repo.set_visible(node_id, req.visible)

    # Update orchestrator state
    await node_manager.set_node_visible(node_id, req.visible)

    return {"status": "success"}


async def reload_all_config():
    """Reload all node configurations."""
    if node_manager._reload_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="A configuration reload is already in progress. Please wait and retry.",
        )

    await node_manager.reload_config()
    return {"status": "success"}


async def reload_single_node(node_id: str):
    """Selectively reload a single node in-place.

    Returns ``NodeReloadResponse`` on success.
    Raises:
        HTTPException(404): Node not in the running DAG.
        HTTPException(409): Reload lock is held.
        HTTPException(500): Reload failed (with rollback info in detail).
    """
    from app.api.v1.schemas.nodes import NodeReloadResponse

    # ── 409: Lock check ────────────────────────────────────────────────────
    if node_manager._reload_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="A configuration reload is already in progress. Please wait and retry.",
        )

    # ── 404: Node existence check ──────────────────────────────────────────
    if node_id not in node_manager.nodes:
        raise HTTPException(
            status_code=404,
            detail=f"Node '{node_id}' not found in running DAG. Ensure the node is enabled.",
        )

    # ── Perform selective reload ───────────────────────────────────────────
    result = await node_manager.selective_reload_node(node_id)

    if result is not None and result.status == "error":
        if result.rolled_back:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Reload failed for node '{node_id}': {result.error_message}. "
                    "Node has been restored to previous configuration."
                ),
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Reload failed for node '{node_id}' and rollback also failed. "
                    "Node is offline. Manual intervention required."
                ),
            )

    ws_topic = getattr(result, "ws_topic", None) if result else None
    duration_ms = getattr(result, "duration_ms", 0.0) if result else 0.0

    return NodeReloadResponse(
        node_id=node_id,
        status="reloaded",
        duration_ms=duration_ms,
        ws_topic=ws_topic,
    )


async def get_reload_status():
    """Return the current state of the reload lock.

    Returns ``ReloadStatusResponse``.
    Spec: .opencode/plans/node-reload-improvement/api-spec.md § 3
    """
    from app.api.v1.schemas.nodes import ReloadStatusResponse

    locked = node_manager._reload_lock.locked()
    active_id: Optional[str] = node_manager._active_reload_node_id

    if not locked:
        estimated_completion_ms = None
    elif active_id is not None:
        estimated_completion_ms = 150   # selective reload estimate
    else:
        estimated_completion_ms = 3000  # full reload estimate

    return ReloadStatusResponse(
        locked=locked,
        reload_in_progress=locked,
        active_reload_node_id=active_id,
        estimated_completion_ms=estimated_completion_ms,
    )


async def get_nodes_status():
    """Returns runtime status of all nodes using the standardised emit_status() interface."""
    status_updates = []

    repo = NodeRepository()
    nodes = repo.list()

    for cnfg in nodes:
        node_id = cnfg["id"]
        node_instance = node_manager.nodes.get(node_id)

        if node_instance and hasattr(node_instance, "emit_status"):
            try:
                status = node_instance.emit_status()
                entry = status.model_dump()
            except Exception as e:
                logger.warning(f"[get_nodes_status] emit_status() failed for {node_id}: {e}")
                continue
        else:
            entry = {
                "node_id": node_id,
                "operational_state": "STOPPED",
                "application_state": None,
                "error_message": "Node instance not found",
                "timestamp": time.time(),
            }

        # Augment with DB metadata that the frontend needs
        entry["category"] = cnfg["category"]
        entry["enabled"] = cnfg["enabled"]
        entry["visible"] = cnfg.get("visible", True)
        entry["name"] = cnfg["name"]
        entry["type"] = cnfg["type"]

        # Derive WebSocket topic (None for invisible nodes)
        if node_instance and hasattr(node_instance, "_ws_topic"):
            entry["topic"] = node_instance._ws_topic
        else:
            entry["topic"] = None

        # Add throttling stats
        throttle_stats = node_manager.get_throttle_stats(node_id)
        entry.update(throttle_stats)

        status_updates.append(entry)

    return {"nodes": status_updates}

