"""Background service that broadcasts node status updates via WebSocket."""
import asyncio
import time
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

from app.services.websocket.manager import manager
from app.services.nodes.instance import node_manager
from app.repositories import NodeRepository
from app.services.shared.topics import slugify_topic_prefix

logger = get_logger("status_broadcaster")

_broadcast_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def _build_status_message() -> Dict[str, Any]:
    """Build the status message payload matching NodesStatusResponse: { nodes: [...] }."""
    node_repo = NodeRepository()
    nodes = node_repo.list()

    nodes_status: List[Dict[str, Any]] = []

    for config in nodes:
        node_id = config["id"]
        node_instance = node_manager.nodes.get(node_id)

        if node_instance and hasattr(node_instance, "get_status"):
            status = node_instance.get_status(node_manager.node_runtime_status)
            # Ensure category and enabled are always present
            status.setdefault("category", config.get("category"))
            status.setdefault("enabled", config.get("enabled", True))
            
            # Auto-generate topic: {slugified_node_name}_{node_id[:8]}
            node_name = getattr(node_instance, "name", node_id)
            safe_name = slugify_topic_prefix(node_name)
            status["topic"] = f"{safe_name}_{node_id[:8]}"
            
            nodes_status.append(status)
        else:
            nodes_status.append({
                "id": node_id,
                "name": config.get("name", node_id),
                "type": config.get("type"),
                "category": config.get("category"),
                "enabled": config.get("enabled", True),
                "running": False,
                "last_error": "Node instance not found",
            })

    return {"nodes": nodes_status}


async def _status_broadcast_loop():
    """Background loop that broadcasts status every 2 seconds."""
    global _stop_event
    
    # Register the status topic
    manager.register_topic("system_status")

    while not _stop_event.is_set():
        try:
            # Build status payload
            status = _build_status_message()
            # Broadcast to all connected clients
            await manager.broadcast("system_status", status)
        except Exception as e:
            logger.exception("[StatusBroadcaster] Error broadcasting status:")
        # Wait 0.5 seconds before next broadcast
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=0.5)
            break  # Stop event was set
        except asyncio.TimeoutError:
            continue  # Timeout is normal, continue loop


def start_status_broadcaster():
    """Start the background status broadcaster task."""
    global _broadcast_task, _stop_event
    if _broadcast_task is not None:
        return  # Already running
    _stop_event = asyncio.Event()
    _broadcast_task = asyncio.create_task(_status_broadcast_loop())
    logger.info("[StatusBroadcaster] Started")


def stop_status_broadcaster():
    """Stop the background status broadcaster task."""
    global _broadcast_task, _stop_event
    if _broadcast_task is None:
        return
    _stop_event.set()
    _broadcast_task.cancel()
    _broadcast_task = None
    _stop_event = None
    logger.info("[StatusBroadcaster] Stopped")
