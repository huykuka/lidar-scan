"""NullMetricsCollector - No-op implementation for disabled metrics.

This module provides a null object pattern implementation that does nothing
when metrics are disabled, allowing the system to run without overhead.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import MetricsSnapshotModel


class NullMetricsCollector:
    """No-op metrics collector for when metrics are disabled.
    
    All methods are no-ops that consume minimal CPU cycles. The snapshot()
    method returns a valid empty MetricsSnapshotModel to maintain API contracts.
    """
    
    def record_node_exec(self, node_id: str, node_name: str, node_type: str, exec_ms: float, point_count: int) -> None:
        """No-op: record DAG node execution metrics."""
        pass
    
    def record_ws_message(self, topic: str, byte_size: int) -> None:
        """No-op: record WebSocket message broadcast."""
        pass
    
    def record_ws_connections(self, topic: str, count: int) -> None:
        """No-op: record WebSocket connection count."""
        pass
    
    def record_endpoint(self, path: str, method: str, latency_ms: float, status_code: int) -> None:
        """No-op: record HTTP endpoint performance.""" 
        pass
    
    def snapshot(self) -> "MetricsSnapshotModel":
        """Return valid empty MetricsSnapshotModel with zero values."""
        # Import here to avoid circular imports
        from .models import (
            MetricsSnapshotModel, DagMetricsModel, WebSocketMetricsModel,
            SystemMetricsModel
        )
        
        return MetricsSnapshotModel(
            timestamp=0.0,
            dag=DagMetricsModel(
                nodes=[],
                total_nodes=0,
                running_nodes=0,
            ),
            websocket=WebSocketMetricsModel(
                topics={},
                total_connections=0,
            ),
            system=SystemMetricsModel(
                cpu_percent=0.0,
                memory_used_mb=0.0,
                memory_total_mb=0.0,
                memory_percent=0.0,
                thread_count=0,
                queue_depth=0,
            ),
            endpoints=[],
        )
    
    def is_enabled(self) -> bool:
        """Always returns False for null collector."""
        return False