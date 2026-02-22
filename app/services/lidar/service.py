"""Compatibility shim.

The Lidar service implementation was moved to `app.services.lidar.sensor` during
backend restructuring. Keep this module so older imports (and reloader
subprocesses) don't crash.
"""

from .core import LidarSensor
from .sensor import LidarService

__all__ = ["LidarSensor", "LidarService"]
