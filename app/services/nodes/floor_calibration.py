"""One-shot floor-plane auto-level shared by all sensor-category source nodes.

Any node that produces a world-frame point cloud and carries a 6-DOF pose can
mix this in to gain a ``calibrate_from_floor`` capability: segment the ground
plane, derive the tilt, and bake a residual roll/pitch correction into the pose.

Host requirements:
    - ``id`` attribute
    - ``pose_params`` (Pose) and ``set_pose(pose)``
    - cache the latest world-frame cloud via ``cache_floor_frame(points)``
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from app.core.logging import get_logger
from app.schemas.pose import Pose

logger = get_logger(__name__)


class FloorCalibrationMixin:
    """Adds one-shot floor-plane auto-level to a pose-bearing source node."""

    _latest_points: Optional[np.ndarray] = None

    def cache_floor_frame(self, points: Optional[np.ndarray]) -> None:
        """Store the latest world-frame cloud for a subsequent calibration."""
        self._latest_points = points

    def calibrate_from_floor(
            self,
            distance_threshold: float = 0.05,
            max_planes: int = 3,
            min_inliers: int = 50,
            verticality_threshold: float = 0.7,
            translate_to_origin: bool = False,
    ) -> Pose:
        """Level the sensor against the floor by segmenting the ground plane.

        Runs RANSAC on the latest world-frame cloud, iterating over the largest
        planes, keeps the near-vertical-normal (near-horizontal surface)
        candidate with the lowest centroid, and applies its tilt as a
        *residual* roll/pitch correction to the current pose. Yaw and position
        are preserved. Repeated calls converge to a flat floor.

        Mutually exclusive with IMU auto-level: raises when it is enabled.

        Args:
            distance_threshold: RANSAC inlier distance (cloud units, meters).
            max_planes: Max planes to segment while searching for the floor.
            min_inliers: Minimum inliers for a plane to be considered.
            verticality_threshold: Min ``|normal·up|`` to accept a plane as
                near-horizontal (0.7 ≈ 45° from vertical).

        Returns:
            The new Pose.

        Raises:
            ValueError: When IMU auto-level is on, no frame is cached yet, or
                no floor-like plane is found.
        """
        if getattr(self, "imu_auto_level", False):
            raise ValueError("IMU auto-level is enabled; disable it before floor calibration.")

        points = self._latest_points
        if points is None or len(points) < min_inliers:
            raise ValueError("No point-cloud frame available yet.")

        import open3d as o3d
        from app.modules.lidar.core import plane_normal_to_roll_pitch

        up = np.array([0.0, 0.0, 1.0])
        xyz = np.asarray(points[:, :3], dtype=np.float64)
        remaining = o3d.geometry.PointCloud()
        remaining.points = o3d.utility.Vector3dVector(xyz)

        best_normal: Optional[np.ndarray] = None
        best_centroid_up = float("inf")

        for _ in range(max_planes):
            if len(remaining.points) < min_inliers:
                break
            plane_model, inliers = remaining.segment_plane(
                distance_threshold=distance_threshold,
                ransac_n=3,
                num_iterations=1000,
            )
            if len(inliers) < min_inliers:
                break

            normal = np.asarray(plane_model[:3], dtype=np.float64)
            n_norm = np.linalg.norm(normal)
            if n_norm > 0:
                normal = normal / n_norm
            if float(np.dot(normal, up)) < 0.0:
                normal = -normal

            inlier_pts = np.asarray(remaining.select_by_index(inliers).points)
            if abs(float(np.dot(normal, up))) >= verticality_threshold:
                centroid_up = float(inlier_pts.mean(axis=0) @ up)
                if centroid_up < best_centroid_up:
                    best_centroid_up = centroid_up
                    best_normal = normal

            remaining = remaining.select_by_index(inliers, invert=True)

        if best_normal is None:
            raise ValueError("No floor-like (near-horizontal) plane found.")

        d_roll, d_pitch = plane_normal_to_roll_pitch(best_normal, up)

        current: Pose = self.pose_params
        new_roll = max(-180.0, min(180.0, current.roll + d_roll))
        new_pitch = max(-180.0, min(180.0, current.pitch + d_pitch))
        # Shift Z so the floor centroid lands at world Z=0 when requested
        new_z = (current.z - best_centroid_up) if translate_to_origin else current.z
        new_pose = Pose(
            x=current.x,
            y=current.y,
            z=new_z,
            roll=new_roll,
            pitch=new_pitch,
            yaw=current.yaw,
        )

        self.set_pose(new_pose)

        from app.repositories.node_orm import NodeRepository
        NodeRepository().update_node_pose(self.id, new_pose)

        logger.info(
            f"[{self.id}] Floor calibration applied: "
            f"roll={new_roll:.2f}° pitch={new_pitch:.2f}° "
            f"(residual Δroll={d_roll:.2f}° Δpitch={d_pitch:.2f}°)"
            + (f" z-shift to origin: {new_z:.4f}m" if translate_to_origin else "")
        )
        return new_pose
