"""
StatusAggregator service - event-driven node status broadcasting.

Spec: .opencode/plans/node-status-standardization/technical.md § 2.3

This service collects status updates from all DAG nodes and broadcasts them
via WebSocket with rate limiting and debouncing to prevent flooding.
"""
import asyncio
import time
from typing import Dict, Optional

from app.core.logging import get_logger
from app.schemas.status import NodeStatusUpdate, SystemStatusBroadcast
from app.services.websocket.manager import manager
from app.services.nodes.instance import node_manager


logger = get_logger("status_aggregator")

# Module-level state for rate limiting (per-node)
_last_emit_time: Dict[str, float] = {}

# Debounce task management
_pending_broadcast_task: Optional[asyncio.Task] = None
_aggregator_running: bool = False

# Rate limit: max 10 updates per node per second
_RATE_LIMIT_SEC = 0.1  # 100ms


def notify_status_change(node_id: str) -> None:
    """
    Public entry point for nodes to signal status changes.
    
    Per-node 100ms rate limit; schedules debounced broadcast task.
    This is the method that nodes call (via their _notify_status callback).
    
    Thread-safe: can be called from Open3D threadpool workers.
    
    Args:
        node_id: The node that changed status
    """
    global _pending_broadcast_task, _aggregator_running
    
    if not _aggregator_running:
        return
    
    # Rate limit check: skip if called too frequently for this node
    now = time.time()
    if node_id in _last_emit_time:
        if now - _last_emit_time[node_id] < _RATE_LIMIT_SEC:
            return  # Drop - rate limited
    
    _last_emit_time[node_id] = now
    
    # Schedule debounced broadcast task if not already pending
    if _pending_broadcast_task is None or _pending_broadcast_task.done():
        _pending_broadcast_task = asyncio.create_task(_broadcast_system_status())


async def _broadcast_system_status() -> None:
    """
    Async broadcast function - collects emit_status() from all live nodes
    and broadcasts via manager.broadcast("system_status", payload).
    
    Includes 100ms debounce sleep to batch multiple rapid status changes.
    """
    # Debounce: wait 100ms to batch multiple rapid changes
    await asyncio.sleep(0.1)
    
    try:
        # Collect status from all registered nodes
        status_updates: list[NodeStatusUpdate] = []
        
        for node_id, node_instance in node_manager.nodes.items():
            if hasattr(node_instance, "emit_status"):
                try:
                    status = node_instance.emit_status()
                    status_updates.append(status)
                except Exception as e:
                    logger.warning(f"[StatusAggregator] Failed to get status from {node_id}: {e}")
            else:
                logger.debug(f"[StatusAggregator] Node {node_id} has no emit_status method - skipping")
        
        # Build broadcast payload
        broadcast = SystemStatusBroadcast(nodes=status_updates)
        payload = broadcast.model_dump()
        
        # Fire-and-forget broadcast (do NOT await inside the node)
        asyncio.create_task(manager.broadcast("system_status", payload))
        
        logger.debug(f"[StatusAggregator] Broadcast {len(status_updates)} node statuses")
    
    except Exception as e:
        logger.exception(f"[StatusAggregator] Error in broadcast_system_status: {e}")


def start_status_aggregator() -> None:
    """
    Register system_status topic and set aggregator running flag.
    
    Called by orchestrator on DAG startup.
    """
    global _aggregator_running
    
    manager.register_topic("system_status")
    _aggregator_running = True
    
    logger.info("[StatusAggregator] Started")


def stop_status_aggregator() -> None:
    """
    Cancel pending broadcast task and reset state.
    
    Called by orchestrator on DAG shutdown.
    """
    global _pending_broadcast_task, _aggregator_running, _last_emit_time
    
    _aggregator_running = False
    
    if _pending_broadcast_task and not _pending_broadcast_task.done():
        _pending_broadcast_task.cancel()
    
    _pending_broadcast_task = None
    _last_emit_time.clear()
    
    logger.info("[StatusAggregator] Stopped")
