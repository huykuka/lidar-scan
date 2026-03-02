"""Pydantic V2 models for performance metrics API responses.

This module defines all data models used for serializing metrics data
in REST endpoints and WebSocket broadcasts. Models match api-spec.md schemas.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class DagNodeMetricsModel(BaseModel):
    """Performance metrics for a single DAG node - matches api-spec.md §4.3"""
    model_config = ConfigDict(from_attributes=True)
    
    node_id: str
    node_name: str
    node_type: str
    last_exec_ms: float
    avg_exec_ms: float
    calls_total: int
    throughput_pps: float
    last_point_count: int
    throttled_count: int
    queue_depth: int
    last_seen_ts: float


class DagMetricsModel(BaseModel):
    """DAG processing metrics - wraps a list of DagNodeMetricsModel"""
    model_config = ConfigDict(from_attributes=True)
    
    nodes: List[DagNodeMetricsModel]
    total_nodes: int
    running_nodes: int


class WsTopicMetricsModel(BaseModel):
    """Per-topic WebSocket metrics - matches api-spec.md §4.5"""
    model_config = ConfigDict(from_attributes=True)
    
    messages_per_sec: float
    bytes_per_sec: float
    active_connections: int
    total_messages: int
    total_bytes: int


class WebSocketMetricsModel(BaseModel):
    """WebSocket metrics collection - matches api-spec.md §4.4"""
    model_config = ConfigDict(from_attributes=True)
    
    topics: Dict[str, WsTopicMetricsModel]
    total_connections: int


class SystemMetricsModel(BaseModel):
    """OS-level system metrics - matches api-spec.md §4.6"""
    model_config = ConfigDict(from_attributes=True)
    
    cpu_percent: float
    memory_used_mb: float
    memory_total_mb: float
    memory_percent: float
    thread_count: int
    queue_depth: int


class EndpointMetricsModel(BaseModel):
    """HTTP endpoint performance metrics - matches api-spec.md §4.7"""
    model_config = ConfigDict(from_attributes=True)
    
    path: str
    method: str
    avg_latency_ms: float
    calls_total: int
    last_status_code: int


class MetricsSnapshotModel(BaseModel):
    """Root envelope for all metrics data - matches api-spec.md §4.1"""
    model_config = ConfigDict(from_attributes=True)
    
    timestamp: float
    dag: DagMetricsModel
    websocket: WebSocketMetricsModel
    system: SystemMetricsModel
    endpoints: List[EndpointMetricsModel]


class PerformanceHealthModel(BaseModel):
    """Lightweight health check response - matches api-spec.md §3.4"""
    model_config = ConfigDict(from_attributes=True)
    
    metrics_enabled: bool
    broadcaster_running: bool
    system_probe_running: bool
    node_count: int
    version: str