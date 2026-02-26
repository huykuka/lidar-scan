"""
Point cloud fusion layer — opt-in, import only when needed.

Usage in app.py:
    from app.services.modules.fusion.service import FusionService

    # Fuse all sensors, no post-processing
    fusion = FusionService(node_manager)

    # Fuse specific sensors only
    fusion = FusionService(node_manager, sensor_ids=["lidar_front", "lidar_rear"])

    # Fuse + run a named pipeline on the merged cloud (same API as generate_lidar)
    fusion = FusionService(
        node_manager,
        topic="fused_reflectors",
        sensor_ids=["lidar_front", "lidar_rear"],
        pipeline_name="reflector",
    )

    # Fusion nodes are now enabled/disabled via the NodeManager and receive
    # data via the on_input(payload) method called by the manager.
"""
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set
import time
import numpy as np

from app.services.websocket.manager import manager
from app.services.modules.lidar.core import transform_points
from app.services.shared.binary import pack_points_binary
from app.services.nodes.base_module import ModuleNode


class FusionService(ModuleNode):
    """
    Listens to transformed frames emitted by LidarService and merges them
    into a single unified point cloud broadcast on `topic`.

    Args:
        node_manager: The LidarService instance to attach to.
        topic:         WebSocket topic name to broadcast the fused cloud on.
        sensor_ids:    Whitelist of sensor IDs to include in the fusion.
                       If None or empty, all registered sensors are used.
    """

    def __init__(
        self,
        node_manager,
        topic: str = "fused_points",
        sensor_ids: Optional[List[str]] = None,
        fusion_id: Optional[str] = None,
    ):
        self._service = node_manager
        self.manager = node_manager
        self.id = fusion_id or f"fusion_{id(self)}"
        self.name = f"Fusion ({self.id[:8]})"
        self._topic = topic
        self._filter: Optional[Set[str]] = set(sensor_ids) if sensor_ids else None
        self._by_topic: bool = False
        self._latest_frames: Dict[str, np.ndarray] = {}
        self._enabled = False
        self._original_handle: Optional[Callable[[Any], Awaitable[None]]] = None

        self.last_broadcast_at: Optional[float] = None
        self.last_broadcast_ts: Optional[float] = None
        self.last_error: Optional[str] = None
        
        # Register the topic so it shows up in the discovery API
        manager.register_topic(self._topic)

    async def on_input(self, payload: Dict[str, Any]):
        """Standard input port for the NodeManager to push data into."""
        await self._on_frame(payload)

    @property
    def topic_filter(self) -> Optional[Set[str]]:
        if self._filter is None:
            return None
        if self._by_topic:
            return self._filter
        return {self._id_to_topic_prefix(sid) for sid in self._filter}

    def _id_to_topic_prefix(self, sensor_id: str) -> str:
        sensor = self._service.nodes.get(sensor_id)
        return getattr(sensor, "topic_prefix", sensor_id)

    def use_topic_prefix_filter(self, enabled: bool = True):
        """Interpret `sensor_ids` as websocket topic prefixes (new behavior in service)."""
        self._by_topic = enabled
        return self

    def enable(self):
        """Activate fusion."""
        self._enabled = True

    def disable(self):
        """Deactivate fusion."""
        self._enabled = False

    async def _on_frame(self, payload):
        """Called after each sensor frame is handled. Extracts points and fuses."""
        if not self._enabled:
            return

        lidar_id = payload.get("lidar_id")
        timestamp = payload.get("timestamp", 0.0)

        # Resolve the emitting sensor's websocket topic prefix
        sensor = self._service.nodes.get(lidar_id)
        topic_prefix = getattr(sensor, "topic_prefix", lidar_id)

        # Skip sensors not in the whitelist
        active_filter = self.topic_filter
        if active_filter and topic_prefix not in active_filter:
            return

        # Get the points from the payload. 
        # Points are already transformed to world space by the LidarSensor node.
        points = payload.get("points")

        if points is None or len(points) == 0:
            return

        self._latest_frames[topic_prefix] = points

        # Wait until all expected sensors have contributed at least once
        expected: Set[str] = active_filter or {getattr(s, "topic_prefix", getattr(s, "id", k)) for k, s in self._service.nodes.items() if getattr(s, "topic_prefix", None)}
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

        # Merge all frames into one cloud off the main thread
        import asyncio
        def _concat():
            return np.concatenate(frames, axis=0)
            
        fused = await asyncio.to_thread(_concat)

        # Forward output to downstream nodes
        fused_payload = {
            "node_id": self.id,
            "points": fused,
            "timestamp": timestamp,
            "count": len(fused)
        }
        await self._service.forward_data(self.id, fused_payload)

        try:
            # Check if anyone is actually listening
            if self._service.has_subscribers(self._topic):
                import asyncio
                binary = await asyncio.to_thread(pack_points_binary, fused, timestamp)
                await manager.broadcast(self._topic, binary)
                
                import time
                self.last_broadcast_at = time.time()
                self.last_broadcast_ts = timestamp
                self.last_error = None
        except Exception as e:
            self.last_error = str(e)

    def get_status(self, runtime_status: Dict[str, Any]) -> Dict[str, Any]:
        """Returns standard status for this node"""
        last_broadcast_at = self.last_broadcast_at
        broadcast_age = time.time() - last_broadcast_at if last_broadcast_at else None
        
        return {
            "id": self.id,
            "name": f"Fusion ({self.id[:8]})",
            "type": "fusion",
            "enabled": self._enabled,
            "running": self._enabled,
            "topic": self._topic,
            "sensor_ids": list(self._filter) if self._filter else [],
            "last_broadcast_at": last_broadcast_at,
            "broadcast_age_seconds": broadcast_age,
            "last_error": self.last_error,
            "input_count": len(self._latest_frames)
        }
