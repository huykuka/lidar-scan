"""
Calibration module for ICP-based LiDAR sensor alignment.

This module provides automatic calibration of multiple LiDAR sensors using
a two-stage registration pipeline (Global Registration + ICP).
"""

from .calibration_node import CalibrationNode

__all__ = ["CalibrationNode"]
