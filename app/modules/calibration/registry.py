"""
Node registry for the calibration module.

This module registers the calibration node type with the DAG orchestrator.
Loaded automatically via discover_modules() at application startup.
"""
from typing import Any, Dict, List
from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)


# --- Schema Definition ---
# Defines how the calibration node appears in the Angular flow-canvas UI

node_schema_registry.register(NodeDefinition(
    type="calibration",
    display_name="ICP Calibration",
    category="calibration",
    description="Automatically align multiple LiDAR sensors using Iterative Closest Point (ICP) registration",
    icon="tune",
    properties=[
        # ICP Settings
        PropertySchema(
            name="icp_method",
            label="ICP Method",
            type="select",
            default="point_to_plane",
            options=[
                {"label": "Point-to-Plane (Recommended)", "value": "point_to_plane"},
                {"label": "Point-to-Point", "value": "point_to_point"}
            ],
            help_text="Point-to-plane is more accurate but requires normals"
        ),
        PropertySchema(
            name="icp_threshold",
            label="ICP Threshold (m)",
            type="number",
            default=0.02,
            min=0.001,
            max=1.0,
            step=0.001,
            help_text="Maximum correspondence distance in meters"
        ),
        PropertySchema(
            name="icp_iterations",
            label="ICP Iterations",
            type="number",
            default=50,
            min=10,
            max=500,
            step=10,
            help_text="Maximum number of ICP iterations"
        ),
        PropertySchema(
            name="translation_only",
            label="Translation Only (XYZ)",
            type="boolean",
            default=False,
            help_text="Only solve for XYZ position, preserve roll/pitch/yaw (use if sensors have IMU)"
        ),
        
        # Global Registration Settings
        PropertySchema(
            name="enable_global_registration",
            label="Enable Global Registration",
            type="boolean",
            default=True,
            help_text="Use FPFH+RANSAC for coarse alignment before ICP"
        ),
        PropertySchema(
            name="global_voxel_size",
            label="Global Voxel Size (m)",
            type="number",
            default=0.05,
            min=0.01,
            max=0.5,
            step=0.01,
            help_text="Downsample voxel size for global registration"
        ),
        PropertySchema(
            name="ransac_threshold",
            label="RANSAC Threshold (m)",
            type="number",
            default=0.075,
            min=0.01,
            max=0.5,
            step=0.005,
            help_text="RANSAC distance threshold in meters"
        ),
        PropertySchema(
            name="ransac_iterations",
            label="RANSAC Iterations",
            type="number",
            default=100000,
            min=10000,
            max=1000000,
            step=10000,
            help_text="Maximum number of RANSAC iterations"
        ),
        
        # Quality Control
        PropertySchema(
            name="min_fitness",
            label="Min Fitness",
            type="number",
            default=0.7,
            min=0.0,
            max=1.0,
            step=0.05,
            help_text="Minimum fitness threshold (0-1, higher is better)"
        ),
        PropertySchema(
            name="max_rmse",
            label="Max RMSE (m)",
            type="number",
            default=0.05,
            min=0.001,
            max=1.0,
            step=0.001,
            help_text="Maximum RMSE threshold in meters (lower is better)"
        ),
        
        # Save Behavior
        PropertySchema(
            name="auto_save",
            label="Auto-Save Results",
            type="boolean",
            default=False,
            help_text="Automatically save calibration without user approval"
        ),
        PropertySchema(
            name="min_fitness_to_save",
            label="Min Fitness for Auto-Save",
            type="number",
            default=0.8,
            min=0.0,
            max=1.0,
            step=0.05,
            help_text="Only auto-save if fitness exceeds this threshold"
        ),
    ],
    inputs=[
        PortSchema(id="sensor_inputs", label="Inputs", multiple=True)
    ]
))


# --- Factory Builder ---

@NodeFactory.register("calibration")
def build_calibration(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """Build a CalibrationNode instance from persisted node configuration."""
    from .calibration_node import CalibrationNode
    
    config = node.get("config", {})
    
    # Validate and normalize configuration values
    normalized_config = {
        "name": node.get("name", "ICP Calibration"),
        "icp_method": config.get("icp_method", "point_to_plane"),
        "icp_threshold": _parse_float(config.get("icp_threshold"), 0.02),
        "icp_iterations": _parse_int(config.get("icp_iterations"), 50),
        "translation_only": _parse_bool(config.get("translation_only"), False),
        "enable_global_registration": _parse_bool(config.get("enable_global_registration"), True),
        "global_voxel_size": _parse_float(config.get("global_voxel_size"), 0.05),
        "ransac_threshold": _parse_float(config.get("ransac_threshold"), 0.075),
        "ransac_iterations": _parse_int(config.get("ransac_iterations"), 100000),
        "min_fitness": _parse_float(config.get("min_fitness"), 0.7),
        "max_rmse": _parse_float(config.get("max_rmse"), 0.05),
        "auto_save": _parse_bool(config.get("auto_save"), False),
        "min_fitness_to_save": _parse_float(config.get("min_fitness_to_save"), 0.8),
    }
    
    return CalibrationNode(
        manager=service_context,
        node_id=node["id"],
        config=normalized_config
    )


# --- Helper Functions ---

def _parse_float(value: Any, default: float) -> float:
    """Safely parse a float value from config."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_int(value: Any, default: int) -> int:
    """Safely parse an int value from config."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _parse_bool(value: Any, default: bool) -> bool:
    """Safely parse a boolean value from config."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    try:
        return bool(value)
    except (ValueError, TypeError):
        return default
