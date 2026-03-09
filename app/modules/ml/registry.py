# ML Node Registry for NodeFactory Integration
"""
Registers ML nodes (semantic segmentation, object detection) with the DAG NodeFactory.
This follows the existing pattern used by other modules like pipeline, lidar, fusion.
"""

from typing import Dict, Any, List
import logging
from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# Conditional imports for optional torch dependency
try:
    import open3d.ml.torch as ml3d
    TORCH_AVAILABLE = True
except ImportError:
    ml3d = None
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)


# --- Schema Definitions ---

# Semantic Segmentation Node Schema
node_schema_registry.register(NodeDefinition(
    type="ml_semantic_segmentation",
    display_name="ML Semantic Segmentation", 
    category="ml",
    description="Per-point semantic labelling using deep learning models",
    icon="psychology",
    properties=[
        PropertySchema(
            name="model_name", 
            label="Model", 
            type="select",
            default="RandLANet",
            options=[
                {"label": "RandLA-Net", "value": "RandLANet"},
                {"label": "KPConv", "value": "KPFCNN"},
                {"label": "PointTransformer", "value": "PointTransformer"},
            ]
        ),
        PropertySchema(
            name="dataset_name", 
            label="Pretrained On", 
            type="select",
            default="SemanticKITTI",
            options=[
                {"label": "SemanticKITTI", "value": "SemanticKITTI"},
                {"label": "S3DIS", "value": "S3DIS"},
                {"label": "Toronto3D", "value": "Toronto3D"},
            ]
        ),
        PropertySchema(
            name="device", 
            label="Device", 
            type="select", 
            default="cpu",
            options=[
                {"label": "CPU", "value": "cpu"}, 
                {"label": "CUDA", "value": "cuda:0"}
            ]
        ),
        PropertySchema(
            name="throttle_ms", 
            label="Throttle (ms)", 
            type="number", 
            default=200, 
            min=0, 
            step=50,
            help_text="Minimum time between inference runs"
        ),
        PropertySchema(
            name="num_points", 
            label="Max Points (subsampling)", 
            type="number", 
            default=45056,
            help_text="Subsample to this many points for inference"
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output (labeled)")]
))

# Object Detection Node Schema  
node_schema_registry.register(NodeDefinition(
    type="ml_object_detection",
    display_name="ML Object Detection",
    category="ml", 
    description="3D bounding box detection using deep learning models",
    icon="view_in_ar",
    properties=[
        PropertySchema(
            name="model_name", 
            label="Model", 
            type="select",
            default="PointPillars",
            options=[
                {"label": "PointPillars", "value": "PointPillars"},
                {"label": "PointRCNN", "value": "PointRCNN"},
            ]
        ),
        PropertySchema(
            name="dataset_name", 
            label="Pretrained On", 
            type="select",
            default="KITTI",
            options=[
                {"label": "KITTI", "value": "KITTI"},
                {"label": "Waymo", "value": "Waymo"},
            ]
        ),
        PropertySchema(
            name="device", 
            label="Device", 
            type="select", 
            default="cpu",
            options=[
                {"label": "CPU", "value": "cpu"}, 
                {"label": "CUDA", "value": "cuda:0"}
            ]
        ),
        PropertySchema(
            name="throttle_ms", 
            label="Throttle (ms)", 
            type="number", 
            default=500, 
            min=0, 
            step=50,
            help_text="Minimum time between inference runs"
        ),
        PropertySchema(
            name="confidence_threshold", 
            label="Confidence Threshold", 
            type="number", 
            default=0.5, 
            step=0.05, 
            min=0.0, 
            max=1.0,
            help_text="Filter detections below this confidence"
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output (with boxes)")]
))


# --- Factory Builders ---

@NodeFactory.register("ml_semantic_segmentation")
def build_semantic_segmentation(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """Build a SemanticSegmentationNode instance."""
    if not TORCH_AVAILABLE:
        from .ml_node import MLNodeStub
        raise RuntimeError("ML nodes require PyTorch. Install: pip install -r requirements-ml.txt")
        
    from .segmentation_node import SemanticSegmentationNode
    
    config = node.get("config", {})
    node_id = node["id"]
    name = node.get("name")
    
    return SemanticSegmentationNode(
        manager=service_context,
        node_id=node_id,
        op_type="ml_semantic_segmentation",
        config=config,
        name=name,
        throttle_ms=config.get("throttle_ms", 200)
    )


@NodeFactory.register("ml_object_detection") 
def build_object_detection(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """Build an ObjectDetectionNode instance."""
    if not TORCH_AVAILABLE:
        from .ml_node import MLNodeStub  
        raise RuntimeError("ML nodes require PyTorch. Install: pip install -r requirements-ml.txt")
        
    from .detection_node import ObjectDetectionNode
    
    config = node.get("config", {})
    node_id = node["id"]
    name = node.get("name")
    
    return ObjectDetectionNode(
        manager=service_context,
        node_id=node_id,
        op_type="ml_object_detection",
        config=config,
        name=name,
        throttle_ms=config.get("throttle_ms", 500)
    )


# This function is called by the module init to register nodes
def register_ml_nodes():
    """Register ML nodes - schemas are auto-registered above via decorators"""
    logger.info(f"ML nodes registered (torch_available={TORCH_AVAILABLE})")
    if not TORCH_AVAILABLE:
        logger.warning("Torch not available - ML nodes will fail with clear error messages")