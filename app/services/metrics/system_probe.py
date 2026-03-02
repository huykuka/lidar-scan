"""System metrics probe for OS-level performance monitoring.

This module provides background collection of system metrics like CPU, memory,
and thread counts at 2 Hz for the performance monitoring dashboard.
"""

import asyncio
import threading
import time
from typing import Optional

from app.core.logging import get_logger
from app.services.nodes.instance import node_manager

logger = get_logger(__name__)

# Module-level task reference
_probe_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


async def _system_probe_loop(registry, stop_event: asyncio.Event) -> None:
    """Background coroutine that collects system metrics at 2 Hz.
    
    Args:
        registry: MetricsRegistry instance to update
        stop_event: Event to signal shutdown
    """
    logger.info("System probe started at 2 Hz")
    
    while not stop_event.is_set():
        try:
            # Lazy import psutil to avoid hard dependency at module load
            import psutil
            
            # Collect system metrics
            cpu_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            thread_count = threading.active_count()
            queue_depth = node_manager.data_queue.qsize() if hasattr(node_manager, 'data_queue') else 0
            
            # Create system metrics sample
            from .registry import SystemMetricsSample
            
            registry.system_metrics = SystemMetricsSample(
                cpu_percent=cpu_percent,
                memory_used_mb=memory.used / (1024 * 1024),  # Convert to MB
                memory_total_mb=memory.total / (1024 * 1024),  # Convert to MB
                memory_percent=memory.percent,
                thread_count=thread_count,
                queue_depth=queue_depth,
            )
            
            logger.debug(f"System metrics: CPU={cpu_percent:.1f}%, Memory={memory.percent:.1f}%, Threads={thread_count}")
            
        except ImportError:
            logger.warning("psutil not available - system metrics disabled")
            break
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
        
        try:
            # Wait for 500ms (2 Hz) or until stop event is set
            await asyncio.wait_for(stop_event.wait(), timeout=0.5)
            break  # Stop event was set
        except asyncio.TimeoutError:
            continue  # Timeout means keep going
    
    logger.info("System probe stopped")


def start_system_probe(registry) -> None:
    """Start the system probe background task.
    
    Args:
        registry: MetricsRegistry instance to populate with system metrics
    """
    global _probe_task, _stop_event
    
    if _probe_task and not _probe_task.done():
        logger.warning("System probe already running")
        return
    
    _stop_event = asyncio.Event()
    _probe_task = asyncio.create_task(_system_probe_loop(registry, _stop_event))
    logger.info("System probe task created")


def stop_system_probe() -> None:
    """Stop the system probe background task."""
    global _probe_task, _stop_event
    
    if _stop_event:
        _stop_event.set()
    
    if _probe_task and not _probe_task.done():
        _probe_task.cancel()
        
    logger.info("System probe stop requested")