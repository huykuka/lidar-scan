# ML Node Registry for NodeFactory Integration
"""
Registers ML nodes (semantic segmentation, object detection) with the DAG NodeFactory.
This follows the existing pattern used by other modules like pipeline, lidar, fusion.
"""

from typing import Dict, Any, List
import logging

# Conditional imports for optional torch dependency
try:
    import open3d.ml.torch as ml3d
    TORCH_AVAILABLE = True
except ImportError:
    ml3d = None
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)


def register_ml_nodes():
    """Register ML node types with NodeFactory"""
    from app.core.node_factory import NodeFactory
    from app.core.node_definitions import (
        NodeDefinition, 
        PropertySchema, 
        PortSchema
    )
    
    if not TORCH_AVAILABLE:
        logger.warning("Torch not available - ML nodes will be registered but will fail at runtime")
    
    # Register semantic segmentation node
    segmentation_definition = NodeDefinition(
        type="ml_semantic_segmentation",
        display_name="ML Semantic Segmentation", 
        category="ml",
        description="Per-point semantic labelling using deep learning",
        icon="psychology",
        properties=[
            PropertySchema(
                name="model_name", 
                label="Model", 
                type="select",
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
                step=50
            ),
            PropertySchema(
                name="num_points", 
                label="Max Points (subsampling)", 
                type="number", 
                default=45056
            ),
        ],
        inputs=[PortSchema(id="in", label="Input")],
        outputs=[PortSchema(id="out", label="Output (labelled)")]
    )
    
    # Register object detection node
    detection_definition = NodeDefinition(
        type="ml_object_detection",
        display_name="ML Object Detection",
        category="ml", 
        description="3D bounding box detection using deep learning",
        icon="view_in_ar",
        properties=[
            PropertySchema(
                name="model_name", 
                label="Model", 
                type="select",
                options=[
                    {"label": "PointPillars", "value": "PointPillars"},
                    {"label": "PointRCNN", "value": "PointRCNN"},
                ]
            ),
            PropertySchema(
                name="dataset_name", 
                label="Pretrained On", 
                type="select",
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
                step=50
            ),
            PropertySchema(
                name="confidence_threshold", 
                label="Confidence Threshold", 
                type="number", 
                default=0.5, 
                step=0.05, 
                min=0.0, 
                max=1.0
            ),
        ],
        inputs=[PortSchema(id="in", label="Input")],
        outputs=[PortSchema(id="out", label="Output (with boxes)")]
    )
    
    # Register node definitions
    NodeFactory.register_node_definition(segmentation_definition)
    NodeFactory.register_node_definition(detection_definition)
    
    # Register node classes (will be imported when TORCH_AVAILABLE)
    if TORCH_AVAILABLE:
        from .segmentation_node import SemanticSegmentationNode
        from .detection_node import ObjectDetectionNode
        
        NodeFactory.register_node_class("ml_semantic_segmentation", SemanticSegmentationNode)
        NodeFactory.register_node_class("ml_object_detection", ObjectDetectionNode)
    else:
        # Register stub classes that will fail with clear error messages
        from .ml_node import MLNodeStub
        NodeFactory.register_node_class("ml_semantic_segmentation", MLNodeStub)
        NodeFactory.register_node_class("ml_object_detection", MLNodeStub)
    
    logger.info(f"Registered ML nodes (torch_available={TORCH_AVAILABLE})")