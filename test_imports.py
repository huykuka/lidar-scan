#!/usr/bin/env python3
"""Quick import test to verify backend implementation structure."""

import sys
import os

# Add the parent directory to the path to import app modules
sys.path.insert(0, '/home/thaiqu/Projects/personnal/performance-monitoring')

def test_core_imports():
    """Test all critical imports."""
    try:
        # Core metrics components
        from app.services.metrics.registry import MetricsRegistry, NodeMetricsSample, WsTopicSample, SystemMetricsSample, EndpointSample
        print("✓ Registry imports successful")
        
        from app.services.metrics.collector import IMetricsCollector, MetricsCollector
        print("✓ Collector imports successful")
        
        from app.services.metrics.null_collector import NullMetricsCollector
        print("✓ NullCollector import successful")
        
        from app.services.metrics.instance import get_metrics_collector, set_metrics_collector
        print("✓ Instance singleton imports successful")
        
        from app.services.metrics.models import MetricsSnapshotModel, DagMetricsModel, PerformanceHealthModel
        print("✓ Pydantic models imports successful")
        
        # Background services
        from app.services.metrics.system_probe import start_system_probe, stop_system_probe
        print("✓ SystemProbe imports successful")
        
        from app.services.metrics.broadcaster import start_metrics_broadcaster, stop_metrics_broadcaster
        print("✓ MetricsBroadcaster imports successful")
        
        from app.services.metrics.open3d_timer import open3d_timer
        print("✓ Open3D timer import successful")
        
        # API and middleware
        from app.middleware.metrics_middleware import MetricsMiddleware
        print("✓ Middleware import successful")
        
        from app.api.v1.metrics import router
        print("✓ API router import successful")
        
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality."""
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

if __name__ == "__main__":
    print("Performance Monitoring Backend - Quick Import Test")
    print("=" * 50)
    
    all_passed = True
    all_passed &= test_core_imports()
    all_passed &= test_basic_functionality()
    
    print("=" * 50)
    if all_passed:
        print("🎉 All tests PASSED - Backend implementation is working!")
    else:
        print("❌ Some tests FAILED")
    
    print()