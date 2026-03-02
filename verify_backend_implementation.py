#!/usr/bin/env python3
"""
Verification script for performance monitoring backend implementation.

This script tests the basic imports and structure without running the full
application to ensure the implementation is correct.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_imports():
    """Test all critical imports to verify implementation structure."""
    try:
        # Core metrics components
        from app.services.metrics.registry import MetricsRegistry, NodeMetricsSample, WsTopicSample, SystemMetricsSample, EndpointSample
        from app.services.metrics.collector import IMetricsCollector, MetricsCollector
        from app.services.metrics.null_collector import NullMetricsCollector
        from app.services.metrics.instance import get_metrics_collector, set_metrics_collector
        from app.services.metrics.models import MetricsSnapshotModel, DagMetricsModel, PerformanceHealthModel
        
        # Background services
        from app.services.metrics.system_probe import start_system_probe, stop_system_probe
        from app.services.metrics.broadcaster import start_metrics_broadcaster, stop_metrics_broadcaster
        from app.services.metrics.open3d_timer import open3d_timer
        
        # API and middleware
        from app.middleware.metrics_middleware import MetricsMiddleware
        
        print("✓ All core metrics imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality without external dependencies."""
    try:
        from app.services.metrics.registry import MetricsRegistry
        from app.services.metrics.collector import MetricsCollector
        from app.services.metrics.null_collector import NullMetricsCollector
        
        # Test registry creation
        registry = MetricsRegistry()
        collector = MetricsCollector(registry)
        null_collector = NullMetricsCollector()
        
        # Test basic collector operations
        collector.record_node_exec("test-node", "Test Node", "test", 1.5, 100)
        collector.record_ws_message("test_topic", 512)
        collector.record_endpoint("/api/test", "GET", 5.0, 200)
        
        # Test null collector
        assert null_collector.is_enabled() == False
        assert collector.is_enabled() == True
        
        print("✓ Basic functionality tests passed")
        return True
        
    except Exception as e:
        print(f"✗ Functionality test error: {e}")
        return False

def test_data_structures():
    """Test data structure integrity."""
    try:
        from app.services.metrics.registry import NodeMetricsSample, WsTopicSample, EndpointSample
        import time
        
        # Test NodeMetricsSample
        node_sample = NodeMetricsSample(
            node_id="test", 
            node_name="Test", 
            node_type="test", 
            last_exec_ms=1.5
        )
        node_sample.exec_times_deque.append(1.0)
        node_sample.exec_times_deque.append(2.0)
        avg = node_sample.avg_exec_ms
        assert avg == 1.5
        
        # Test WsTopicSample 
        ws_sample = WsTopicSample(topic="test")
        ws_sample.messages_window.append((time.monotonic(), 512))
        assert ws_sample.total_messages == 0  # Only updated by collector
        
        # Test EndpointSample
        endpoint_sample = EndpointSample(path="/test", method="GET")
        endpoint_sample.latency_times_deque.append(5.0)
        endpoint_sample.latency_times_deque.append(3.0)
        avg_latency = endpoint_sample.avg_latency_ms
        assert avg_latency == 4.0
        
        print("✓ Data structure tests passed")
        return True
        
    except Exception as e:
        print(f"✗ Data structure test error: {e}")
        return False

if __name__ == "__main__":
    print("Performance Monitoring Backend - Verification Script")
    print("=" * 50)
    
    all_passed = True
    
    all_passed &= test_imports()
    all_passed &= test_basic_functionality()  
    all_passed &= test_data_structures()
    
    print("=" * 50)
    if all_passed:
        print("🎉 All verification tests PASSED")
        print("Backend implementation is ready for integration!")
    else:
        print("❌ Some tests FAILED")
        print("Please check the implementation for errors.")
    
    sys.exit(0 if all_passed else 1)