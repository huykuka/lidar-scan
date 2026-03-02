"""
Unit tests for MetricsRegistry and related data structures.

Tests the core metrics collection and aggregation logic without 
external dependencies or I/O operations.
"""

import time
from collections import deque

import pytest

from app.services.metrics.registry import (
    MetricsRegistry, 
    NodeMetricsSample, 
    WsTopicSample, 
    EndpointSample,
    SystemMetricsSample
)
from app.services.metrics.collector import MetricsCollector
from app.services.metrics.null_collector import NullMetricsCollector


def test_record_node_exec_creates_entry():
    """Test that record_node_exec() with a new node_id creates a NodeMetricsSample."""
    registry = MetricsRegistry()
    collector = MetricsCollector(registry)
    
    # Record execution for a new node
    collector.record_node_exec("test-node-123", "Test Node", "test_module", 2.5, 1000)
    
    # Verify entry was created
    assert "test-node-123" in registry.node_metrics
    sample = registry.node_metrics["test-node-123"]
    
    assert sample.node_id == "test-node-123"
    assert sample.node_name == "Test Node"
    assert sample.node_type == "test_module"
    assert sample.last_exec_ms == 2.5
    assert sample.calls_total == 1
    assert sample.last_point_count == 1000
    assert len(sample.exec_times_deque) == 1
    assert sample.exec_times_deque[0] == 2.5


def test_avg_exec_ms_rolling_window():
    """Test that avg_exec_ms correctly averages the last 60 samples, discarding older ones."""
    registry = MetricsRegistry()
    collector = MetricsCollector(registry)
    
    node_id = "rolling-test"
    
    # Add 70 execution times (0.5ms to 35.0ms in 0.5ms increments)
    for i in range(70):
        exec_ms = 0.5 + (i * 0.5)  # 0.5, 1.0, 1.5, ..., 35.0
        collector.record_node_exec(node_id, "Test Node", "test", exec_ms, 100)
    
    sample = registry.node_metrics[node_id]
    
    # Verify deque is capped at 60
    assert len(sample.exec_times_deque) == 60
    
    # Verify only last 60 values are present (5.5ms to 35.0ms)
    # First 10 values (0.5 to 5.0ms) are discarded, keeping indices 10-69 (5.5 to 35.0ms)
    expected_values = [5.5 + (i * 0.5) for i in range(60)]
    actual_values = list(sample.exec_times_deque)
    
    for expected, actual in zip(expected_values, actual_values):
        assert abs(actual - expected) < 0.01  # Allow small floating point errors
    
    # Verify average is computed correctly
    expected_avg = sum(expected_values) / len(expected_values)
    assert abs(sample.avg_exec_ms - expected_avg) < 0.05


def test_ws_metrics_per_second_windowing():
    """Test that messages_per_sec only counts messages in the last 1-sec window."""
    registry = MetricsRegistry()
    collector = MetricsCollector(registry)
    
    # Mock time.monotonic() to control timestamps
    base_time = 1000.0
    timestamps = [base_time, base_time + 0.2, base_time + 0.8, base_time + 1.2, base_time + 2.5]
    
    # Record messages at specific times
    with pytest.MonkeyPatch.context() as mp:
        time_iter = iter(timestamps)
        mp.setattr(time, "monotonic", lambda: next(time_iter))
        
        # Record 5 messages at the controlled timestamps
        for _ in range(5):
            collector.record_ws_message("test_topic", 1000)
    
    sample = registry.ws_topic_metrics["test_topic"]
    
    # At t=2.5s, only messages from t>=1.5s should be counted
    # That's the messages at t=2.5s (only the last one)
    # But since we're using an iterator, let's check the actual logic
    
    # Manually verify the windowing logic
    current_time = timestamps[-1]  # 2.5
    cutoff = current_time - 1.0    # 1.5
    
    # Count messages that should be in window
    expected_count = sum(1 for ts, _ in sample.messages_window if ts >= cutoff)
    
    # Mock the current time for the property call
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(time, "monotonic", lambda: current_time)
        actual_count = sample.messages_per_sec
    
    assert actual_count == expected_count
    assert sample.total_messages == 5  # All messages counted in total


def test_snapshot_serialization():
    """Test that registry.snapshot() returns a valid MetricsSnapshotModel with no validation errors."""
    registry = MetricsRegistry()
    collector = MetricsCollector(registry)
    
    # Add some test data
    collector.record_node_exec("node1", "Node 1", "test", 1.5, 500)
    collector.record_ws_message("topic1", 2048)
    collector.record_endpoint("/api/test", "GET", 10.5, 200)
    
    # Add system metrics
    registry.system_metrics = SystemMetricsSample(
        cpu_percent=25.5,
        memory_used_mb=512.0,
        memory_total_mb=8192.0,
        memory_percent=6.25,
        thread_count=12,
        queue_depth=3
    )
    
    # Get snapshot and verify it's valid
    snapshot = registry.snapshot()
    
    # Basic structure checks
    assert snapshot.timestamp > 0
    assert len(snapshot.dag.nodes) == 1
    assert snapshot.dag.total_nodes == 1
    assert len(snapshot.websocket.topics) == 1
    assert snapshot.system.cpu_percent == 25.5
    assert len(snapshot.endpoints) == 1
    
    # Test serialization round-trip
    data_dict = snapshot.model_dump()
    assert isinstance(data_dict, dict)
    assert "timestamp" in data_dict
    assert "dag" in data_dict
    
    # Verify we can recreate from dict
    from app.services.metrics.models import MetricsSnapshotModel
    reconstructed = MetricsSnapshotModel.model_validate(data_dict)
    assert reconstructed.dag.total_nodes == 1


def test_null_collector_is_enabled():
    """Test that NullMetricsCollector().is_enabled() returns False."""
    null_collector = NullMetricsCollector()
    assert null_collector.is_enabled() is False


def test_null_collector_snapshot_is_valid():
    """Test that NullMetricsCollector().snapshot() returns empty but valid MetricsSnapshotModel."""
    null_collector = NullMetricsCollector()
    snapshot = null_collector.snapshot()
    
    # Verify structure is valid but empty
    assert snapshot.timestamp == 0.0
    assert len(snapshot.dag.nodes) == 0
    assert snapshot.dag.total_nodes == 0
    assert snapshot.dag.running_nodes == 0
    assert len(snapshot.websocket.topics) == 0
    assert snapshot.websocket.total_connections == 0
    assert snapshot.system.cpu_percent == 0.0
    assert len(snapshot.endpoints) == 0
    
    # Verify it can be serialized
    data_dict = snapshot.model_dump()
    assert isinstance(data_dict, dict)