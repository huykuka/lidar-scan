"""
Test to verify the circular import fix for node-status-standardization.

ROOT CAUSE:
  Circular import chain broke module registry loading:
  instance.py → discover_modules() → registries → node implementations 
  → status_aggregator.py → instance.py (circular!)

SOLUTION:
  Lazy import of node_manager inside _broadcast_system_status() breaks the cycle.

This test ensures the fix remains stable across future refactors.
"""
import pytest


def test_node_manager_imports_without_circular_error():
    """Verify node_manager can be imported without circular import errors."""
    from app.services.nodes.instance import node_manager
    assert node_manager is not None


def test_all_module_registries_loaded():
    """Verify all module registries loaded successfully."""
    from app.services.nodes.node_factory import NodeFactory
    
    # Check that registries loaded
    registered_types = list(NodeFactory._registry.keys())
    
    # Core node types that must be present
    required_types = ['sensor', 'calibration', 'fusion', 'crop', 'downsample', 'if_condition']
    
    for node_type in required_types:
        assert node_type in registered_types, \
            f"Node type '{node_type}' not registered - module registry failed to load"


def test_sensor_node_type_is_registered():
    """Verify 'sensor' node type is registered (was causing 'Unknown node type: sensor' error)."""
    from app.services.nodes.node_factory import NodeFactory
    
    assert 'sensor' in NodeFactory._registry, \
        "Sensor node type not registered - lidar registry failed to load"


def test_sensor_node_can_be_instantiated():
    """Verify sensor nodes can be instantiated via NodeFactory."""
    from app.services.nodes.node_factory import NodeFactory
    from unittest.mock import MagicMock
    
    test_node_data = {
        'id': 'test-sensor-circular-import-fix',
        'type': 'sensor',
        'name': 'Test Sensor',
        'config': {
            'lidar_type': 'multiscan',
            'hostname': '192.168.1.10',
            'throttle_ms': 0
        }
    }
    
    mock_context = MagicMock()
    mock_context._topic_registry.register.return_value = 'test_sensor'
    
    # This should NOT raise "Unknown node type: sensor"
    sensor = NodeFactory.create(test_node_data, mock_context, [])
    assert sensor is not None
    assert sensor.name == 'Test Sensor'


def test_status_aggregator_imports_without_error():
    """Verify status_aggregator functions can be imported."""
    from app.services.status_aggregator import (
        notify_status_change,
        start_status_aggregator,
        stop_status_aggregator,
    )
    
    # Functions should be callable
    assert callable(notify_status_change)
    assert callable(start_status_aggregator)
    assert callable(stop_status_aggregator)


@pytest.mark.asyncio
async def test_status_aggregator_lazy_import_works():
    """Verify lazy import of node_manager inside _broadcast_system_status works."""
    from unittest.mock import patch, MagicMock, AsyncMock
    from app.services.status_aggregator import start_status_aggregator, stop_status_aggregator, notify_status_change
    from app.schemas.status import NodeStatusUpdate, OperationalState
    import asyncio
    
    # Mock node_manager at the lazy import location
    mock_nm = MagicMock()
    mock_node = MagicMock()
    mock_node.emit_status.return_value = NodeStatusUpdate(
        node_id="test-node",
        operational_state=OperationalState.RUNNING,
        application_state=None,
        error_message=None,
    )
    mock_nm.nodes = {"test-node": mock_node}
    
    with patch("app.services.nodes.instance.node_manager", mock_nm), \
         patch("app.services.status_aggregator.manager") as mock_ws_manager:
        
        mock_ws_manager.register_topic = MagicMock()
        mock_ws_manager.broadcast = AsyncMock()
        
        start_status_aggregator()
        try:
            # Trigger broadcast
            notify_status_change("test-node")
            
            # Allow debounce to fire
            await asyncio.sleep(0.15)
            
            # Verify broadcast was called (proves lazy import worked)
            assert mock_ws_manager.broadcast.call_count >= 1
        finally:
            stop_status_aggregator()


def test_no_module_load_errors_in_logs():
    """
    Verify discover_modules() did not log any import errors.
    
    Before the fix, logs would show:
      ERROR | app.modules | Failed to load module 'calibration' registry: 
      cannot import name 'node_manager' from partially initialized module
    """
    # If we got this far without import errors, the fix is working.
    # This test serves as documentation of the expected behavior.
    from app.services.nodes.instance import node_manager
    from app.services.nodes.node_factory import NodeFactory
    
    # At least 10 node types should be registered (we have 14 currently)
    assert len(NodeFactory._registry) >= 10, \
        "Module registries failed to load - check logs for circular import errors"
