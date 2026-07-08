"""
Point cloud fusion layer — opt-in, import only when needed.

Usage in app.py:
    from app.modules.fusion.service import FusionService

    # Fuse all sensors, no post-processing
    fusion = FusionService(node_manager)

    # Fuse specific sensors only
    fusion = FusionService(node_manager, sensor_ids=["lidar_front", "lidar_rear"])

    # Fusion nodes are now enabled/disabled via the NodeManager and receive
    # data via the on_input(payload) method called by the manager.
    
    # WebSocket topic is auto-generated as: {node_name}_{node_id[:8]}
"""
from typing import Any, Dict, List, Optional, Set
import time

import numpy as np

from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change


class FusionService(ModuleNode):
    """
    Listens to transformed frames emitted by LidarService and merges them
    into a single unified point cloud.

    Args:
        node_manager: The NodeManager instance.
        sensor_ids:   Whitelist of sensor IDs to include in the fusion.
                      If None or empty, all registered sensors are used.
        fusion_id:    Unique identifier for this fusion node.
    """

    def __init__(
            self,
            node_manager,
            sensor_ids: Optional[List[str]] = None,
            fusion_id: Optional[str] = None,
            throttle_ms: float = 0
    ):
        self._service = node_manager
        self.manager = node_manager
        self.id = fusion_id or f"fusion_{id(self)}"
        self.name = "Fusion"
        self._filter: Optional[Set[str]] = set(sensor_ids) if sensor_ids else None
        self._latest_frames: Dict[str, np.ndarray] = {}
        self._enabled = True

        self.last_broadcast_at: Optional[float] = None
        self.last_broadcast_ts: Optional[float] = None
        self.last_error: Optional[str] = None
        self.processing_time_ms: float = 0.0

    async def on_input(self, payload: Dict[str, Any]):
        """Standard input port for the NodeManager to push data into."""
        await self._on_frame(payload)

    def enable(self):
        """Activate fusion."""
        self._enabled = True
        notify_status_change(self.id)

    def disable(self):
        """Deactivate fusion."""
        self._enabled = False
        notify_status_change(self.id)

    async def _on_frame(self, payload):
        """Called after each sensor frame is handled. Extracts points and fuses."""
        if not self._enabled:
            return

        # Key each frame by its immediate DAG predecessor. Every node stamps
        # node_id=self.id before forwarding, so node_id is the direct upstream
        # sender — which is what expected_sensors (built from downstream_map
        # edges) contains. Fall back to lidar_id for real sensors that only
        # stamp lidar_id (== their own id) and omit node_id. Preferring lidar_id
        # would break fusion whenever an intermediate node (e.g. a Crop filter)
        # sits between the sensor and the fusion node, because lidar_id stays
        # pinned to the original leaf sensor instead of the direct predecessor.
        source_id = payload.get("node_id") or payload.get("lidar_id")
        timestamp = payload.get("timestamp", 0.0)

        if not source_id:
            return

        # Skip sensors not in the whitelist (if filter is set)
        if self._filter and source_id not in self._filter:
            return

        # Get the points from the payload. 
        # Points are already transformed to world space by the LidarSensor node.
        points = payload.get("points")

        if points is None or len(points) == 0:
            return

        # Store latest frame from this sensor
        prev_count = len(self._latest_frames)
        self._latest_frames[source_id] = points
        if len(self._latest_frames) > prev_count:
            # New sensor contributed — notify status change
            notify_status_change(self.id)

        # Determine which sensors we're waiting for
        if self._filter:
            # If filter is set, wait for those specific sensors
            expected_sensors = self._filter
        else:
            # If no filter, wait for every node directly wired into this fusion
            # node in the DAG. This works for any source type (LiDAR, playback,
            # pcd injection, upstream filters), not just nodes with topic_prefix.
            expected_sensors = {
                src_id
                for src_id, edges in self._service.downstream_map.items()
                for edge in edges
                if edge.get("target_id") == self.id
            }

        # Wait until all expected sensors have contributed at least once.
        # Require at least one expected sensor to avoid fusing an empty set.
        if not expected_sensors or not expected_sensors.issubset(self._latest_frames.keys()):
            return

        # Collect frames for fusion
        frames = [self._latest_frames[sid] for sid in expected_sensors]

        start_time = time.time()

        # Check for column mismatch
        num_cols = {f.shape[1] for f in frames}
        if len(num_cols) > 1:
            # Fallback to XYZ (3 columns) if fields don't match (e.g. Real Lidar 16-cols + Sim PCD 3-cols)
            frames = [f[:, :3] for f in frames]

        # Merge all frames into one cloud — np.concatenate is fast enough
        # (~10-50 µs for 2-4 sensor frames) to run directly on the event loop.
        fused = np.concatenate(frames, axis=0)
        self.processing_time_ms = (time.time() - start_time) * 1000

        fused_payload = {
            "node_id": self.id,
            "points": fused,
            "timestamp": timestamp,
            "count": len(fused)
        }

        self.last_broadcast_at = time.time()
        self.last_broadcast_ts = timestamp
        self.last_error = None

        await self.manager.forward_data(self.id, fused_payload)

    def emit_status(self) -> NodeStatusUpdate:
        """Return standardised status for this fusion node.

        State mapping:
        - ``last_error`` set → ERROR, fusing=0, red, propagate error_message
        - ``_enabled == False`` → STOPPED, fusing=0, gray
        - enabled, no frames yet → RUNNING, fusing=0, gray
        - enabled, frames present → RUNNING, fusing=len(_latest_frames), blue

        Returns:
            NodeStatusUpdate with operational_state and fusing application_state
        """
        cycle_ms = round(self.processing_time_ms, 1) if self.processing_time_ms else None

        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(
                    label="fusing",
                    value=0,
                    color="red",
                ),
                error_message=self.last_error,
                cycle_time_ms=cycle_ms,
            )

        if not self._enabled:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.STOPPED,
                application_state=ApplicationState(
                    label="fusing",
                    value=0,
                    color="gray",
                ),
                cycle_time_ms=cycle_ms,
            )

        frame_count = len(self._latest_frames)
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="fusing",
                value=frame_count,
                color="blue" if frame_count > 0 else "gray",
            ),
            cycle_time_ms=cycle_ms,
        )
