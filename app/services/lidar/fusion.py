"""
Point cloud fusion layer — opt-in, import only when needed.

Usage in app.py:
    from app.services.lidar.fusion import FusionService

    # Fuse all sensors, no post-processing
    fusion = FusionService(lidar_service)

    # Fuse specific sensors only
    fusion = FusionService(lidar_service, sensor_ids=["lidar_front", "lidar_rear"])

    # Fuse + run a named pipeline on the merged cloud (same API as generate_lidar)
    fusion = FusionService(
        lidar_service,
        topic="fused_reflectors",
        sensor_ids=["lidar_front", "lidar_rear"],
        pipeline_name="reflector",
    )

    fusion.enable()
"""
from typing import Dict, List, Optional, Set

import numpy as np

from app.pipeline import PipelineFactory, PipelineName
from app.pipeline.base import PointCloudPipeline
from app.services.websocket.manager import manager


class FusionService:
    """
    Listens to transformed frames emitted by LidarService and merges them
    into a single unified point cloud broadcast on `topic`.

    Args:
        lidar_service: The LidarService instance to attach to.
        topic:         WebSocket topic name to broadcast the fused cloud on.
        sensor_ids:    Whitelist of sensor IDs to include in the fusion.
                       If None or empty, all registered sensors are used.
        pipeline_name: Name of a registered pipeline to run on the fused cloud
                       before broadcasting. Resolved via PipelineFactory — same
                       API as generate_lidar(pipeline_name=...).
    """

    def __init__(self, lidar_service, topic: str = "fused_points",
                 sensor_ids: Optional[List[str]] = None,
                 pipeline_name: Optional[PipelineName] = None):
        self._service = lidar_service
        self._topic = topic
        self._filter: Optional[Set[str]] = set(sensor_ids) if sensor_ids else None
        self._pipeline: Optional[PointCloudPipeline] = (
            PipelineFactory.get(pipeline_name, lidar_id="fusion") if pipeline_name else None
        )
        self._latest_frames: Dict[str, np.ndarray] = {}
        self._enabled = False
        self._original_handle = None

    def enable(self):
        """Activate fusion — patches LidarService to intercept frames."""
        if self._enabled:
            return
        self._enabled = True
        self._original_handle = self._service._handle_incoming_data

        async def _patched_handle(payload):
            await self._original_handle(payload)
            await self._on_frame(payload)

        self._service._handle_incoming_data = _patched_handle

    def disable(self):
        """Deactivate fusion — restores the original handler."""
        if not self._enabled or self._original_handle is None:
            return
        self._service._handle_incoming_data = self._original_handle
        self._enabled = False

    async def _on_frame(self, payload):
        """Called after each sensor frame is handled. Extracts points and fuses."""
        lidar_id = payload.get("lidar_id")
        timestamp = payload.get("timestamp", 0.0)

        # Skip sensors not in the whitelist
        if self._filter and lidar_id not in self._filter:
            return

        # Get the points from the payload
        if payload.get("processed"):
            data = payload.get("data") or {}
            points = data.get("points")
        else:
            points = payload.get("points")

        if points is None or len(points) == 0:
            return

        # Apply the sensor's transformation to bring into world space
        sensor = next((s for s in self._service.sensors if s.id == lidar_id), None)
        if sensor is not None:
            points = self._service._transform_points(points, sensor.transformation)

        self._latest_frames[lidar_id] = points

        # Wait until all expected sensors have contributed
        expected: Set[str] = self._filter or {s.id for s in self._service.sensors}
        if not expected.issubset(self._latest_frames.keys()):
            return

        # Merge all frames into one cloud
        fused = np.concatenate(list(self._latest_frames.values()), axis=0)

        # Optionally run a pipeline on the fused cloud
        if self._pipeline is not None:
            result = self._pipeline.process(fused)
            fused = result.get("points", fused)
            if fused is None or len(fused) == 0:
                return

        binary = self._service._pack_binary(fused, timestamp)
        await manager.broadcast(self._topic, binary)
