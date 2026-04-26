"""
Node registry for the detection module.

Registers the ``object_detection_3d`` node type with the DAG orchestrator.
Loaded automatically via ``discover_modules()`` at application startup.

Side-effects executed at import time:

* ``node_schema_registry`` receives the ``NodeDefinition`` for
  ``object_detection_3d``.
* ``NodeFactory`` receives the builder via the ``@register`` decorator.

The model registry is also populated here so that the UI select dropdown
shows all available backends.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition,
    PortSchema,
    PropertySchema,
    node_schema_registry,
)

# ── Import model modules to trigger @register_model decorators ──────────
# Each model file uses @register_model which populates MODEL_REGISTRY.
# Guarded so the node still registers even when torch is not installed.
try:
    from app.modules.detection.models import pointpillars as _pp  # noqa: F401
except ImportError:
    pass

from app.modules.detection.models.base import get_available_models

# ── Build dynamic model options list ────────────────────────────────────
_model_options = get_available_models()
if not _model_options:
    # Fallback so the schema is always valid even without torch
    _model_options = [{"label": "PointPillars (KITTI)", "value": "pointpillars"}]

# ─────────────────────────────────────────────────────────────────────────
# Schema Definition
# ─────────────────────────────────────────────────────────────────────────

node_schema_registry.register(
    NodeDefinition(
        type="object_detection_3d",
        display_name="3D Object Detection",
        category="detection",
        description=(
            "ML-based real-time 3D object detection on point cloud streams. "
            "Emits 3D bounding boxes as shape overlays and forwards detection "
            "metadata downstream.  Model backend is swappable via configuration."
        ),
        icon="view_in_ar",
        websocket_enabled=True,
        properties=[
            PropertySchema(
                name="model",
                label="Model",
                type="select",
                options=_model_options,
                default="pointpillars",
                help_text="Select the ML model backend for 3D detection.",
            ),
            PropertySchema(
                name="checkpoint",
                label="Checkpoint Path",
                type="string",
                default="",
                help_text=(
                    "Absolute path to the .pth model weights file. "
                    "For PointPillars, use KITTI-pretrained weights."
                ),
            ),
            PropertySchema(
                name="device",
                label="Device",
                type="select",
                options=[
                    {"label": "CPU", "value": "cpu"},
                    {"label": "CUDA (GPU)", "value": "cuda"},
                ],
                default="cpu",
                help_text="Inference device. CUDA requires a compatible GPU and torch+cuda.",
            ),
            PropertySchema(
                name="confidence_threshold",
                label="Confidence Threshold",
                type="number",
                default=0.3,
                min=0.0,
                max=1.0,
                step=0.05,
                help_text="Discard detections with confidence below this value.",
            ),
            PropertySchema(
                name="nms_iou_threshold",
                label="NMS IoU Threshold",
                type="number",
                default=0.5,
                min=0.0,
                max=1.0,
                step=0.05,
                help_text=(
                    "BEV IoU threshold for Non-Maximum Suppression. "
                    "Lower = more aggressive suppression of overlapping boxes."
                ),
            ),
            PropertySchema(
                name="max_detections",
                label="Max Detections",
                type="number",
                default=50,
                min=1,
                max=200,
                step=1,
                help_text="Maximum number of detections to emit per frame.",
            ),
            PropertySchema(
                name="throttle_ms",
                label="Throttle (ms)",
                type="number",
                default=100,
                min=0,
                step=10,
                help_text=(
                    "Minimum time between processed frames (0 = no limit). "
                    "Recommended: 100ms+ for CPU inference."
                ),
            ),
        ],
        inputs=[PortSchema(id="in", label="Point Cloud Input")],
        outputs=[PortSchema(id="out", label="Detections Output")],
    )
)


# ─────────────────────────────────────────────────────────────────────────
# Factory Builder
# ─────────────────────────────────────────────────────────────────────────

@NodeFactory.register("object_detection_3d")
def build_detection_node(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """Build a DetectionNode from persisted node configuration."""
    from app.modules.detection.node import DetectionNode  # lazy import

    config = node.get("config", {})

    throttle_ms = config.get("throttle_ms", 100)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 100.0

    return DetectionNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name", "3D Detection"),
        config=config,
        throttle_ms=throttle_ms,
    )
