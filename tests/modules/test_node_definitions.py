"""
Unit tests for node definition schema validation.

Verifies that all registered node types correctly populate the websocket_enabled field
and that streaming vs non-streaming nodes have appropriate flag values.
"""
import pytest
from app.services.nodes.schema import node_schema_registry

# Import all module registries to trigger registration
import app.modules.lidar.registry
import app.modules.fusion.registry
import app.modules.pipeline.registry
import app.modules.calibration.registry
import app.modules.flow_control.if_condition.registry


def test_all_definitions_have_websocket_enabled_field():
    """Ensure all registered node types explicitly define websocket_enabled."""
    definitions = node_schema_registry.get_all()
    assert len(definitions) > 0, "No node definitions registered"
    
    for defn in definitions:
        assert hasattr(defn, 'websocket_enabled'), \
            f"{defn.type} missing websocket_enabled field"
        assert isinstance(defn.websocket_enabled, bool), \
            f"{defn.type} websocket_enabled is not boolean"


def test_streaming_nodes_have_websocket_enabled_true():
    """Streaming node types must have websocket_enabled=True."""
    streaming_types = [
        "sensor", "fusion", 
        "crop", "downsample", "outlier_removal", "radius_outlier_removal",
        "plane_segmentation", "clustering", "boundary_detection", 
        "filter_by_key", "debug_save"
    ]
    
    for node_type in streaming_types:
        defn = node_schema_registry.get(node_type)
        assert defn is not None, f"Definition for {node_type} not found"
        assert defn.websocket_enabled is True, \
            f"{node_type} should have websocket_enabled=True"


def test_non_streaming_nodes_have_websocket_enabled_false():
    """Non-streaming node types must have websocket_enabled=False."""
    non_streaming_types = ["calibration", "if_condition"]
    
    for node_type in non_streaming_types:
        defn = node_schema_registry.get(node_type)
        assert defn is not None, f"Definition for {node_type} not found"
        assert defn.websocket_enabled is False, \
            f"{node_type} should have websocket_enabled=False"


def test_api_response_includes_websocket_enabled():
    """Verify websocket_enabled field is included in API serialization."""
    # Get a sample definition and convert to dict to simulate API serialization
    sensor_defn = node_schema_registry.get("sensor")
    assert sensor_defn is not None, "Sensor definition not found"
    
    # Pydantic model_dump() simulates JSON serialization
    sensor_dict = sensor_defn.model_dump()
    
    assert "websocket_enabled" in sensor_dict, \
        "websocket_enabled field missing from serialized output"
    assert isinstance(sensor_dict["websocket_enabled"], bool), \
        "websocket_enabled should serialize as boolean"
    assert sensor_dict["websocket_enabled"] is True, \
        "Sensor node should have websocket_enabled=True"
    
    # Test non-streaming node
    calibration_defn = node_schema_registry.get("calibration")
    assert calibration_defn is not None, "Calibration definition not found"
    
    calibration_dict = calibration_defn.model_dump()
    assert "websocket_enabled" in calibration_dict, \
        "websocket_enabled field missing from calibration output"
    assert calibration_dict["websocket_enabled"] is False, \
        "Calibration node should have websocket_enabled=False"
