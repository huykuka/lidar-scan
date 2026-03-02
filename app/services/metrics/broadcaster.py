"""MetricsBroadcaster - Background task for pushing metrics to WebSocket clients.

This module provides a background service that broadcasts MetricsSnapshot
payloads to the 'system_metrics' WebSocket topic at 1 Hz, following the
exact architecture pattern of status_broadcaster.py.
"""

import asyncio
import os
from typing import Optional

from app.core.logging import get_logger
from app.services.websocket.manager import manager
from .instance import get_metrics_collector

logger = get_logger("metrics_broadcaster")

# Module-level task and stop event (same pattern as status_broadcaster)
_broadcast_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


async def _metrics_broadcast_loop(stop_event: asyncio.Event) -> None:
    """Background loop that broadcasts metrics at configurable Hz.
    
    Args:
        stop_event: Event to signal shutdown
    """
    # Get broadcast frequency from environment (default 1 Hz)
    hz = float(os.getenv("METRICS_BROADCAST_HZ", "1"))
    interval = 1.0 / hz
    
    # Register the metrics topic
    manager.register_topic("system_metrics")
    logger.info(f"Metrics broadcaster started at {hz} Hz")
    
    while not stop_event.is_set():
        try:
            collector = get_metrics_collector()
            
            # Skip broadcast if metrics are disabled (NullCollector)
            if not collector.is_enabled():
                logger.debug("Metrics disabled, skipping broadcast")
            else:
                # Get snapshot and serialize to dict
                snapshot = collector.snapshot()
                payload_dict = snapshot.model_dump()
                
                # Broadcast to system_metrics topic
                await manager.broadcast("system_metrics", payload_dict)
                logger.debug(f"Broadcasted metrics snapshot with {len(payload_dict.get('dag', {}).get('nodes', []))} nodes")
        
        except Exception as e:
            logger.error(f"Error in metrics broadcast loop: {e}")
        
        try:
            # Wait for interval or until stop event is set
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break  # Stop event was set
        except asyncio.TimeoutError:
            continue  # Timeout is normal, continue loop
    
    logger.info("Metrics broadcaster stopped")


def start_metrics_broadcaster() -> None:
    """Start the background metrics broadcaster task."""
    global _broadcast_task, _stop_event
    
    if _broadcast_task is not None and not _broadcast_task.done():
        logger.warning("Metrics broadcaster already running")
        return
    
    _stop_event = asyncio.Event()
    _broadcast_task = asyncio.create_task(_metrics_broadcast_loop(_stop_event))
    logger.info("Metrics broadcaster task created")


def stop_metrics_broadcaster() -> None:
    """Stop the background metrics broadcaster task."""
    global _broadcast_task, _stop_event
    
    if _stop_event:
        _stop_event.set()
        
    if _broadcast_task and not _broadcast_task.done():
        _broadcast_task.cancel()
        
    _broadcast_task = None
    _stop_event = None
    logger.info("Metrics broadcaster stop requested")