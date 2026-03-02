"""MetricsRegistry - In-memory state for all performance metrics.

This module provides the core data structures for storing metrics in session-only
memory. All metric state lives in deques and dicts with fixed memory bounds.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import MetricsSnapshotModel


@dataclass
class NodeMetricsSample:
    """Performance metrics for a single DAG node.
    
    Tracks execution times, throughput, and call counts with rolling windows.
    """
    node_id: str
    node_name: str
    node_type: str
    last_exec_ms: float
    exec_times_deque: deque = field(default_factory=lambda: deque(maxlen=60))
    calls_total: int = 0
    last_point_count: int = 0
    last_seen_ts: float = field(default_factory=time.monotonic)
    throttled_count: int = 0
    throughput_pps: float = 0.0  # Updated externally each 1-sec window
    
    @property
    def avg_exec_ms(self) -> float:
        """Rolling average execution time over the last 60 samples."""
        if not self.exec_times_deque:
            return 0.0
        return sum(self.exec_times_deque) / len(self.exec_times_deque)


@dataclass  
class WsTopicSample:
    """WebSocket topic performance metrics.
    
    Tracks message counts, byte throughput, and connection counts.
    """
    topic: str
    messages_window: deque = field(default_factory=lambda: deque(maxlen=60))  # (ts, byte_size) tuples
    total_messages: int = 0
    total_bytes: int = 0
    active_connections: int = 0
    
    @property
    def messages_per_sec(self) -> float:
        """Messages broadcast in the last 1-second window."""
        now = time.monotonic()
        cutoff = now - 1.0
        count = sum(1 for ts, _ in self.messages_window if ts >= cutoff)
        return float(count)
    
    @property
    def bytes_per_sec(self) -> float:
        """Bytes broadcast in the last 1-second window.""" 
        now = time.monotonic()
        cutoff = now - 1.0
        total = sum(size for ts, size in self.messages_window if ts >= cutoff)
        return float(total)


@dataclass
class SystemMetricsSample:
    """OS-level system performance metrics.
    
    Matches api-spec.md §4.6 SystemMetrics schema.
    """
    cpu_percent: float
    memory_used_mb: float
    memory_total_mb: float
    memory_percent: float
    thread_count: int
    queue_depth: int


@dataclass
class EndpointSample:
    """HTTP endpoint performance metrics.
    
    Tracks latency and call counts for FastAPI routes.
    """
    path: str
    method: str
    latency_times_deque: deque = field(default_factory=lambda: deque(maxlen=60))
    calls_total: int = 0
    last_status_code: int = 200
    
    @property
    def avg_latency_ms(self) -> float:
        """Rolling average latency over the last 60 samples."""
        if not self.latency_times_deque:
            return 0.0
        return sum(self.latency_times_deque) / len(self.latency_times_deque)


class MetricsRegistry:
    """Singleton registry holding all in-memory metric state.
    
    This is a pure data-holding class with no external I/O. All operations
    are GIL-protected dict/deque mutations for minimal overhead.
    """
    
    def __init__(self):
        # DAG node metrics keyed by node_id
        self.node_metrics: Dict[str, NodeMetricsSample] = {}
        
        # WebSocket topic metrics keyed by topic name  
        self.ws_topic_metrics: Dict[str, WsTopicSample] = {}
        
        # System-level metrics (latest sample only)
        self.system_metrics: Optional[SystemMetricsSample] = None
        
        # HTTP endpoint metrics keyed by "{method}:{path}"
        self.endpoint_metrics: Dict[str, EndpointSample] = {}
    
    def snapshot(self) -> "MetricsSnapshotModel":
        """Serialize current state into a Pydantic MetricsSnapshotModel.
        
        This method will be implemented after models.py is created (BE-10).
        """
        # Import here to avoid circular imports
        from .models import (
            MetricsSnapshotModel, DagMetricsModel, DagNodeMetricsModel,
            WebSocketMetricsModel, WsTopicMetricsModel, SystemMetricsModel,
            EndpointMetricsModel
        )
        
        # Convert node metrics
        dag_nodes = [
            DagNodeMetricsModel(
                node_id=sample.node_id,
                node_name=sample.node_name, 
                node_type=sample.node_type,
                last_exec_ms=sample.last_exec_ms,
                avg_exec_ms=sample.avg_exec_ms,
                calls_total=sample.calls_total,
                throughput_pps=sample.throughput_pps,
                last_point_count=sample.last_point_count,
                throttled_count=sample.throttled_count,
                queue_depth=0,  # This will be updated by system probe
                last_seen_ts=sample.last_seen_ts,
            )
            for sample in self.node_metrics.values()
        ]
        
        dag_metrics = DagMetricsModel(
            nodes=dag_nodes,
            total_nodes=len(dag_nodes),
            running_nodes=len([n for n in dag_nodes if time.monotonic() - n.last_seen_ts < 5.0])
        )
        
        # Convert WebSocket metrics
        ws_topics = {
            topic: WsTopicMetricsModel(
                messages_per_sec=sample.messages_per_sec,
                bytes_per_sec=sample.bytes_per_sec,
                active_connections=sample.active_connections,
                total_messages=sample.total_messages,
                total_bytes=sample.total_bytes,
            )
            for topic, sample in self.ws_topic_metrics.items()
        }
        
        ws_metrics = WebSocketMetricsModel(
            topics=ws_topics,
            total_connections=sum(sample.active_connections for sample in self.ws_topic_metrics.values())
        )
        
        # Convert system metrics
        system = SystemMetricsModel(
            cpu_percent=self.system_metrics.cpu_percent if self.system_metrics else 0.0,
            memory_used_mb=self.system_metrics.memory_used_mb if self.system_metrics else 0.0,
            memory_total_mb=self.system_metrics.memory_total_mb if self.system_metrics else 0.0,
            memory_percent=self.system_metrics.memory_percent if self.system_metrics else 0.0,
            thread_count=self.system_metrics.thread_count if self.system_metrics else 0,
            queue_depth=self.system_metrics.queue_depth if self.system_metrics else 0,
        )
        
        # Convert endpoint metrics
        endpoints = [
            EndpointMetricsModel(
                path=sample.path,
                method=sample.method,
                avg_latency_ms=sample.avg_latency_ms,
                calls_total=sample.calls_total,
                last_status_code=sample.last_status_code,
            )
            for sample in self.endpoint_metrics.values()
        ]
        
        return MetricsSnapshotModel(
            timestamp=time.time(),
            dag=dag_metrics,
            websocket=ws_metrics,
            system=system,
            endpoints=endpoints,
        )
    
    def reset(self) -> None:
        """Reset all metrics state. Used for testing."""
        self.node_metrics.clear()
        self.ws_topic_metrics.clear()
        self.system_metrics = None
        self.endpoint_metrics.clear()