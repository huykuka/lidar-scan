"""
StatusAggregator service - event-driven node status broadcasting.

Spec: .opencode/plans/node-status-standardization/technical.md § 2.3

This service collects status updates from all DAG nodes and broadcasts them
via WebSocket with rate limiting and debouncing to prevent flooding.

CIRCULAR IMPORT FIX:
  node_manager is imported lazily inside _broadcast_system_status() to break
  the circular dependency: instance.py -> discover_modules() -> registries -> 
  node implementations -> status_aggregator.py -> instance.py (circular!)
"""
import asyncio
import time
from typing import Dict, Optional, TYPE_CHECKING

from app.core.logging import get_logger
from app.schemas.status import NodeStatusUpdate, SystemStatusBroadcast
from app.services.websocket.manager import manager

if TYPE_CHECKING:
    from app.services.nodes.orchestrator import NodeManager

logger = get_logger("status_aggregator")

# Module-level state for rate limiting (per-node)
_last_emit_time: Dict[str, float] = {}

# Debounce task management
_pending_broadcast_task: Optional[asyncio.Task] = None
_aggregator_running: bool = False

# Continuous background polling task
_poll_task: Optional[asyncio.Task] = None
_POLL_INTERVAL_SEC = 1.0  # broadcast full status every 1s when subscribers are present

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


async def _collect_and_broadcast() -> None:
    """
    Core broadcast: collect emit_status() from all nodes and push to WebSocket.
    No debounce — callers control timing.
    """
    try:
        from app.services.nodes.instance import node_manager

        status_updates: list[NodeStatusUpdate] = []

        for node_id, node_instance in node_manager.nodes.items():
            if hasattr(node_instance, "emit_status"):
                try:
                    status_updates.append(node_instance.emit_status())
                except Exception as e:
                    logger.warning(f"[StatusAggregator] Failed to get status from {node_id}: {e}")
            else:
                logger.debug(f"[StatusAggregator] Node {node_id} has no emit_status method - skipping")

        payload = SystemStatusBroadcast(nodes=status_updates).model_dump()
        asyncio.create_task(manager.broadcast("system_status", payload))

        logger.debug(f"[StatusAggregator] Broadcast {len(status_updates)} node statuses")

    except Exception as e:
        logger.exception(f"[StatusAggregator] Error in broadcast_system_status: {e}")


async def _broadcast_system_status() -> None:
    """
    Async broadcast function - collects emit_status() from all live nodes
    and broadcasts via manager.broadcast("system_status", payload).
    
    Includes 100ms debounce sleep to batch multiple rapid status changes.
    
    Uses lazy import of node_manager to avoid circular dependency during
    module initialization.
    """
    # Debounce: wait 100ms to batch multiple rapid changes
    await asyncio.sleep(0.1)
    # Skip if no client connected during the debounce window
    if manager.has_subscribers("system_status"):
        await _collect_and_broadcast()


async def _poll_loop() -> None:
    """
    Background task: broadcasts full system status every _POLL_INTERVAL_SEC.

    Runs for the lifetime of the aggregator so clients that reconnect after a
    page reload always receive an up-to-date snapshot within one interval,
    even when no organic state change has occurred.
    """
    while _aggregator_running:
        await asyncio.sleep(_POLL_INTERVAL_SEC)
        if not _aggregator_running:
            break
        # Skip collection and serialisation entirely when no client is listening
        if manager.has_subscribers("system_status"):
            await _collect_and_broadcast()


def start_status_aggregator() -> None:
    """
    Register system_status topic and set aggregator running flag.
    
    Called by orchestrator on DAG startup.
    """
    global _aggregator_running, _poll_task
    
    manager.register_topic("system_status")
    _aggregator_running = True
    _poll_task = asyncio.create_task(_poll_loop())
    
    logger.info("[StatusAggregator] Started")


def stop_status_aggregator() -> None:
    """
    Cancel pending broadcast task, poll loop, and reset state.
    
    Called by orchestrator on DAG shutdown.
    """
    global _pending_broadcast_task, _aggregator_running, _last_emit_time, _poll_task
    
    _aggregator_running = False
    
    if _pending_broadcast_task and not _pending_broadcast_task.done():
        _pending_broadcast_task.cancel()
    _pending_broadcast_task = None

    if _poll_task and not _poll_task.done():
        _poll_task.cancel()
    _poll_task = None

    _last_emit_time.clear()
    
    logger.info("[StatusAggregator] Stopped")
