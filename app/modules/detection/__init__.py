"""
Detection module — ML-based object detection for 3D point clouds.

Provides a pluggable ``DetectionNode`` that runs inference using swappable
model backends (PointPillars, etc.) and emits 3D bounding box shapes
for the Three.js viewer overlay.
"""
