"""Open3D async timer context manager for operation performance tracking.

This module provides an async context manager that measures Open3D operations
run via asyncio.to_thread() and stores the timing data in metrics registry.
"""

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.core.logging import get_logger
from .instance import get_metrics_collector
from .registry import NodeMetricsSample

logger = get_logger(__name__)


@asynccontextmanager
async def open3d_timer(operation_name: str, node_id: str) -> AsyncGenerator[None, None]:
    """Async context manager for timing Open3D operations.
    
    Usage example:
    ```python
    async with open3d_timer("voxel_downsample", node_id):
        result = await asyncio.to_thread(o3d.geometry.PointCloud.voxel_down_sample, ...)
    ```
    
    Args:
        operation_name: Name of the Open3D operation (e.g., 'voxel_downsample')
        node_id: ID of the DAG node performing the operation
        
    Yields:
        None - execution proceeds within the timed block
    """
    t0 = time.monotonic_ns()
    
    try:
        yield
    finally:
        # Calculate execution time
        exec_ms = (time.monotonic_ns() - t0) / 1_000_000.0
        
        try:
            collector = get_metrics_collector()
            
            # Get the collector's registry to access node metrics directly
            if hasattr(collector, 'registry'):
                registry = collector.registry
                
                # Ensure node metrics sample exists
                if node_id not in registry.node_metrics:
                    registry.node_metrics[node_id] = NodeMetricsSample(
                        node_id=node_id,
                        node_name=f"node_{node_id[:8]}",  # Placeholder name
                        node_type="open3d_processor",      # Placeholder type
                        last_exec_ms=0.0,
                    )
                
                node_sample = registry.node_metrics[node_id]
                
                # Initialize open3d_ops dict if it doesn't exist
                if not hasattr(node_sample, 'open3d_ops'):
                    node_sample.open3d_ops = {}
                
                # Update operation metrics
                if operation_name not in node_sample.open3d_ops:
                    node_sample.open3d_ops[operation_name] = {
                        "last_ms": 0.0,
                        "avg_ms": 0.0,
                        "calls": 0
                    }
                
                op_metrics = node_sample.open3d_ops[operation_name]
                op_metrics["last_ms"] = exec_ms
                op_metrics["calls"] += 1
                
                # Update rolling average (simple approach)
                if op_metrics["calls"] == 1:
                    op_metrics["avg_ms"] = exec_ms
                else:
                    # Exponential moving average with alpha=0.1
                    alpha = 0.1
                    op_metrics["avg_ms"] = (1 - alpha) * op_metrics["avg_ms"] + alpha * exec_ms
                
                logger.debug(f"Open3D timer: {operation_name} on {node_id} took {exec_ms:.2f}ms")
            
        except Exception as e:
            # Never let metrics errors affect the actual Open3D operation
            logger.debug(f"Error recording Open3D metrics for {operation_name}: {e}")