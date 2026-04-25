"""Compatibility shim.

The Lidar service implementation was moved to `app.services.nodes.manager` during
backend restructuring. Keep this module so older imports (and reloader
subprocesses) don't crash.
"""

from .node import LidarSensor

__all__ = ["LidarSensor"]
