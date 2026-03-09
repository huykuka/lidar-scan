# ML Module for Open3D-ML Integration
"""
Open3D-ML Integration Module

This module provides machine learning capabilities for the lidar-standalone
point cloud processing system through integration with Open3D-ML.

Features:
- Semantic point cloud segmentation
- 3D object detection
- Model registry for singleton model management
- WebSocket LIDR v2 protocol support
"""

from .registry import register_ml_nodes

__all__ = ['register_ml_nodes']

def init_ml_module():
    """Initialize ML module by registering nodes with NodeFactory"""
    register_ml_nodes()