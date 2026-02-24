from typing import List, Any, Callable
import time
import json
import os
import open3d as o3d
import numpy as np
from ..base import PipelineOperation, PointCloudPipeline, _tensor_map_keys

class Visualize(PipelineOperation):
    """Renders the point cloud with Open3D's visualizer for quick inspection."""

    def __init__(self, window_name: str = "LiDAR Viewer", point_size: float = 1.5,
                 width: int = 960, height: int = 600, blocking: bool = True,
                 stay_seconds: float = 1.0):
        self.window_name = window_name
        self.point_size = point_size
        self.width = width
        self.height = height
        self.blocking = blocking
        self.stay_seconds = stay_seconds

    def _to_legacy(self, pcd: Any) -> o3d.geometry.PointCloud:
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            return pcd.to_legacy()
        return pcd

    def apply(self, pcd: Any):
        legacy_pcd = self._to_legacy(pcd)
        point_count = len(legacy_pcd.points)
        if point_count == 0:
            return pcd, {"visualized": False, "reason": "empty cloud"}

        vis = o3d.visualization.Visualizer()
        vis.create_window(window_name=self.window_name, width=self.width, height=self.height, visible=True)
        vis.add_geometry(legacy_pcd)
        render_opt = vis.get_render_option()
        render_opt.point_size = self.point_size

        vis.update_geometry(legacy_pcd)
        vis.poll_events()
        vis.update_renderer()

        if self.blocking:
            vis.run()
        else:
            deadline = time.time() + max(self.stay_seconds, 0.1)
            while time.time() < deadline:
                vis.poll_events()
                vis.update_renderer()
                time.sleep(0.01)
        vis.destroy_window()

        return pcd, {"visualized": True, "points": point_count}

