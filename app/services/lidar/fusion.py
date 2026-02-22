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
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

import numpy as np

from app.pipeline import PipelineFactory
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
                 pipeline_name: Optional[str] = None):
        self._service = lidar_service
        self._topic = topic
        self._filter: Optional[Set[str]] = set(sensor_ids) if sensor_ids else None
        self._by_topic: bool = False
        self._pipeline: Optional[PointCloudPipeline] = None
        if pipeline_name:
            self._pipeline = PipelineFactory.get(pipeline_name, lidar_id="fusion")
        self._latest_frames: Dict[str, np.ndarray] = {}
        self._enabled = False
        self._original_handle: Optional[Callable[[Any], Awaitable[None]]] = None
        
        # Register the topic so it shows up in the discovery API
        manager.register_topic(self._topic)

    @property
    def topic_filter(self) -> Optional[Set[str]]:
        if self._filter is None:
            return None
        if self._by_topic:
            return self._filter
        return {self._id_to_topic_prefix(sid) for sid in self._filter}

    def _id_to_topic_prefix(self, sensor_id: str) -> str:
        sensor = next((s for s in self._service.sensors if s.id == sensor_id), None)
        return getattr(sensor, "topic_prefix", sensor_id)

    def use_topic_prefix_filter(self, enabled: bool = True):
        """Interpret `sensor_ids` as websocket topic prefixes (new behavior in service)."""
        self._by_topic = enabled
        return self

    def enable(self):
        """Activate fusion — patches LidarService to intercept frames."""
        if self._enabled:
            return
        self._enabled = True
        # LidarService._handle_incoming_data is an async function; keep the type checker happy.
        self._original_handle = self._service._handle_incoming_data  # type: ignore[assignment]

        async def _patched_handle(payload):
            original = self._original_handle
            if original is not None:
                await original(payload)
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

        # Resolve the emitting sensor's websocket topic prefix
        sensor = next((s for s in self._service.sensors if s.id == lidar_id), None)
        topic_prefix = getattr(sensor, "topic_prefix", lidar_id)

        # Skip sensors not in the whitelist
        active_filter = self.topic_filter
        if active_filter and topic_prefix not in active_filter:
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
        if sensor is not None:
            points = self._service._transform_points(points, sensor.transformation)

        self._latest_frames[topic_prefix] = points

        # Wait until all expected sensors have contributed at least once
        expected: Set[str] = active_filter or {getattr(s, "topic_prefix", s.id) for s in self._service.sensors}
        if not expected.issubset(self._latest_frames.keys()):
            missing = expected - self._latest_frames.keys()
            # Only print at start or if it's been a while (to avoid spamming)
            # For debugging, we'll print it once per unique missing set
            if not hasattr(self, '_last_missing') or self._last_missing != missing:
                print(f"[Fusion] Waiting for sensors: {missing}. Have: {list(self._latest_frames.keys())}")
                self._last_missing = missing
            return

        if hasattr(self, '_last_missing'):
            print(f"[Fusion] All sensors active: {list(expected)}. Starting fusion.")
            delattr(self, '_last_missing')

        # Collect frames for fusion
        frames = [self._latest_frames[sid] for sid in expected]

        # Check for column mismatch
        num_cols = {f.shape[1] for f in frames}
        if len(num_cols) > 1:
            # Fallback to XYZ (3 columns) if fields don't match (e.g. Real Lidar 16-cols + Sim PCD 3-cols)
            frames = [f[:, :3] for f in frames]

        # Merge all frames into one cloud
        fused = np.concatenate(frames, axis=0)

        # Optionally run a pipeline on the fused cloud
        if self._pipeline is not None:
            result = self._pipeline.process(fused)
            fused = result.get("points", fused)
            if fused is None or len(fused) == 0:
                return

        binary = self._service._pack_binary(fused, timestamp)
        await manager.broadcast(self._topic, binary)
