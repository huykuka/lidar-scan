"""IMetricsCollector Protocol and concrete implementations.

This module defines the interface contract for metrics collection and provides
two implementations: MetricsCollector (real collection) and NullMetricsCollector
(no-op for when metrics are disabled).
"""

import json
import time
from typing import Protocol, TYPE_CHECKING

from .registry import (
    MetricsRegistry, NodeMetricsSample, WsTopicSample, EndpointSample
)

if TYPE_CHECKING:
    from .models import MetricsSnapshotModel


class IMetricsCollector(Protocol):
    """Protocol defining the interface for metrics collection.
    
    This interface is used by all instrumentation points throughout the system
    to record performance data in a decoupled manner.
    """
    
    def record_node_exec(self, node_id: str, node_name: str, node_type: str, exec_ms: float, point_count: int) -> None:
        """Record DAG node execution metrics.
        
        Args:
            node_id: Unique identifier for the DAG node
            node_name: Human-readable display name
            node_type: Module type string (e.g. 'sick_lidar')
            exec_ms: Execution time in milliseconds
            point_count: Number of points processed in this execution
        """
        ...
    
    def record_ws_message(self, topic: str, byte_size: int) -> None:
        """Record WebSocket message broadcast.
        
        Args:
            topic: WebSocket topic name
            byte_size: Size of the message in bytes
        """
        ...
    
    def record_ws_connections(self, topic: str, count: int) -> None:
        """Record WebSocket connection count for a topic.
        
        Args:
            topic: WebSocket topic name
            count: Current number of active connections
        """
        ...
    
    def record_endpoint(self, path: str, method: str, latency_ms: float, status_code: int) -> None:
        """Record HTTP endpoint performance.
        
        Args:
            path: API route path (e.g. '/api/nodes')
            method: HTTP method ('GET', 'POST', etc.)
            latency_ms: Request latency in milliseconds
            status_code: HTTP status code
        """
        ...
    
    def snapshot(self) -> "MetricsSnapshotModel":
        """Get current metrics snapshot as Pydantic model."""
        ...
    
    def is_enabled(self) -> bool:
        """Check if metrics collection is enabled."""
        ...


class MetricsCollector:
    """Real metrics collector implementation.
    
    Stores metrics data in a MetricsRegistry instance and provides 
    access to current metrics state.
    """
    
    def __init__(self, registry: MetricsRegistry):
        """Initialize with a metrics registry.
        
        Args:
            registry: MetricsRegistry instance to store data in
        """
        self.registry = registry
    
    def record_node_exec(self, node_id: str, node_name: str, node_type: str, exec_ms: float, point_count: int) -> None:
        """Record DAG node execution metrics."""
        # Get or create node metrics sample
        if node_id not in self.registry.node_metrics:
            self.registry.node_metrics[node_id] = NodeMetricsSample(
                node_id=node_id,
                node_name=node_name,
                node_type=node_type,
                last_exec_ms=exec_ms,
            )
        
        sample = self.registry.node_metrics[node_id]
        
        # Update metrics
        sample.last_exec_ms = exec_ms
        sample.exec_times_deque.append(exec_ms)
        sample.calls_total += 1
        sample.last_point_count = point_count
        sample.last_seen_ts = time.monotonic()
    
    def record_ws_message(self, topic: str, byte_size: int) -> None:
        """Record WebSocket message broadcast."""
        # Get or create topic metrics sample
        if topic not in self.registry.ws_topic_metrics:
            self.registry.ws_topic_metrics[topic] = WsTopicSample(topic=topic)
        
        sample = self.registry.ws_topic_metrics[topic]
        
        # Record message with timestamp
        current_time = time.monotonic()
        sample.messages_window.append((current_time, byte_size))
        sample.total_messages += 1
        sample.total_bytes += byte_size
    
    def record_ws_connections(self, topic: str, count: int) -> None:
        """Record WebSocket connection count for a topic."""
        # Get or create topic metrics sample
        if topic not in self.registry.ws_topic_metrics:
            self.registry.ws_topic_metrics[topic] = WsTopicSample(topic=topic)
        
        sample = self.registry.ws_topic_metrics[topic]
        sample.active_connections = count
    
    def record_endpoint(self, path: str, method: str, latency_ms: float, status_code: int) -> None:
        """Record HTTP endpoint performance."""
        key = f"{method}:{path}"
        
        # Get or create endpoint metrics sample
        if key not in self.registry.endpoint_metrics:
            self.registry.endpoint_metrics[key] = EndpointSample(
                path=path,
                method=method,
            )
        
        sample = self.registry.endpoint_metrics[key]
        
        # Update metrics
        sample.latency_times_deque.append(latency_ms)
        sample.calls_total += 1
        sample.last_status_code = status_code
    
    def snapshot(self) -> "MetricsSnapshotModel":
        """Get current metrics snapshot as Pydantic model."""
        return self.registry.snapshot()
    
    def is_enabled(self) -> bool:
        """Check if metrics collection is enabled."""
        return True