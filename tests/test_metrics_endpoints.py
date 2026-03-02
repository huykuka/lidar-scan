"""
Integration tests for metrics REST API endpoints.

Tests the HTTP endpoints using FastAPI TestClient to verify
correct responses, status codes, and error handling.
"""

import pytest
from fastapi.testclient import TestClient

from app.app import app
from app.services.metrics import MetricsRegistry, MetricsCollector, NullMetricsCollector, set_metrics_collector
from app.services.metrics.registry import SystemMetricsSample


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def enable_metrics():
    """Enable real metrics collector for testing."""
    registry = MetricsRegistry()
    collector = MetricsCollector(registry)
    set_metrics_collector(collector)
    
    # Add some test data
    collector.record_node_exec("test-node", "Test Node", "test_type", 2.5, 1000)
    collector.record_ws_message("test_topic", 512)
    collector.record_endpoint("/api/test", "GET", 5.0, 200)
    
    registry.system_metrics = SystemMetricsSample(
        cpu_percent=15.5,
        memory_used_mb=256.0,
        memory_total_mb=4096.0,
        memory_percent=6.25,
        thread_count=8,
        queue_depth=2
    )
    
    yield collector
    
    # Reset to null collector
    set_metrics_collector(NullMetricsCollector())


@pytest.fixture
def disable_metrics():
    """Disable metrics collector for testing."""
    set_metrics_collector(NullMetricsCollector())
    yield
    # Cleanup handled by other fixtures


def test_get_metrics_returns_200_when_enabled(client, enable_metrics):
    """Test that with real MetricsCollector, endpoint returns 200."""
    response = client.get("/api/v1/metrics/")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure matches MetricsSnapshotModel
    assert "timestamp" in data
    assert "dag" in data
    assert "websocket" in data
    assert "system" in data
    assert "endpoints" in data
    
    # Verify some data is present
    assert len(data["dag"]["nodes"]) > 0
    assert data["dag"]["nodes"][0]["node_id"] == "test-node"
    assert data["system"]["cpu_percent"] == 15.5


def test_get_metrics_returns_503_when_disabled(client, disable_metrics):
    """Test that with NullMetricsCollector, GET /api/metrics returns 503."""
    response = client.get("/api/v1/metrics/")
    
    assert response.status_code == 503
    data = response.json()
    assert "detail" in data
    assert "disabled" in data["detail"].lower()


def test_health_performance_always_200(client, enable_metrics):
    """Test that GET /api/health/performance returns 200 regardless of collector type."""
    # Test with enabled metrics
    response = client.get("/api/v1/metrics/health/performance")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "metrics_enabled" in data
    assert "broadcaster_running" in data
    assert "system_probe_running" in data
    assert "node_count" in data
    assert "version" in data
    
    assert data["metrics_enabled"] is True
    assert data["node_count"] >= 0
    
    # Test with disabled metrics
    set_metrics_collector(NullMetricsCollector())
    response = client.get("/api/v1/metrics/health/performance")
    
    assert response.status_code == 200
    data = response.json()
    assert data["metrics_enabled"] is False
    assert data["node_count"] == 0


def test_dag_endpoint_schema(client, enable_metrics):
    """Test that response validates against DagMetricsModel."""
    response = client.get("/api/v1/metrics/dag")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify DagMetricsModel structure
    assert "nodes" in data
    assert "total_nodes" in data
    assert "running_nodes" in data
    
    assert isinstance(data["nodes"], list)
    assert isinstance(data["total_nodes"], int)
    assert isinstance(data["running_nodes"], int)
    
    # Verify node structure if nodes present
    if data["nodes"]:
        node = data["nodes"][0]
        required_fields = [
            "node_id", "node_name", "node_type", "last_exec_ms",
            "avg_exec_ms", "calls_total", "throughput_pps",
            "last_point_count", "throttled_count", "queue_depth", "last_seen_ts"
        ]
        for field in required_fields:
            assert field in node


def test_websocket_endpoint_schema(client, enable_metrics):
    """Test that response validates against WebSocketMetricsModel."""
    response = client.get("/api/v1/metrics/websocket")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify WebSocketMetricsModel structure
    assert "topics" in data
    assert "total_connections" in data
    
    assert isinstance(data["topics"], dict)
    assert isinstance(data["total_connections"], int)
    
    # Verify topic structure if topics present
    for topic_name, topic_data in data["topics"].items():
        required_fields = [
            "messages_per_sec", "bytes_per_sec", "active_connections",
            "total_messages", "total_bytes"
        ]
        for field in required_fields:
            assert field in topic_data
            assert isinstance(topic_data[field], (int, float))