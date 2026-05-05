"""
Truck bin detection algorithm for open-top dump trucks.

Detects the cargo bin from a 3D point cloud by:
1. Optional voxel downsampling for performance
2. PCA-based orientation alignment
3. Horizontal floor plane detection (RANSAC)
4. Vertical wall plane detection (RANSAC on residual points)
5. Bin boundary extraction from wall geometry
6. Volume computation from detected dimensions

Designed for open-top dump trucks where the bin is visible from above
or from the side via LiDAR.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import open3d as o3d

logger = logging.getLogger(__name__)


@dataclass
class BinDetectionResult:
    """Result of a truck bin detection analysis."""

    detected: bool
    length: float = 0.0
    width: float = 0.0
    height: float = 0.0
    volume: float = 0.0
    floor_centroid: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    floor_normal: List[float] = field(default_factory=lambda: [0.0, 0.0, 1.0])
    bin_points: Optional[np.ndarray] = None
    wall_count: int = 0
    floor_inlier_count: int = 0

    def to_dict(self) -> dict:
        return {
            "detected": self.detected,
            "length": round(self.length, 3),
            "width": round(self.width, 3),
            "height": round(self.height, 3),
            "volume": round(self.volume, 3),
            "floor_centroid": [round(v, 3) for v in self.floor_centroid],
            "floor_normal": [round(v, 4) for v in self.floor_normal],
            "wall_count": self.wall_count,
            "floor_inlier_count": self.floor_inlier_count,
        }


@dataclass
class _PlaneResult:
    """Internal representation of a detected plane."""

    normal: np.ndarray
    centroid: np.ndarray
    inlier_indices: np.ndarray
    inlier_count: int


class BinDetector:
    """Detects and measures the cargo bin of open-top dump trucks.

    Args:
        min_bin_length:           Minimum valid bin length (m).
        min_bin_width:            Minimum valid bin width (m).
        min_bin_height:           Minimum valid bin wall height (m).
        floor_distance_threshold: RANSAC inlier distance for floor plane (m).
        wall_distance_threshold:  RANSAC inlier distance for wall planes (m).
        floor_ransac_n:           RANSAC sample size for floor fitting.
        floor_ransac_iterations:  RANSAC max iterations for floor fitting.
        wall_min_points:          Minimum inlier count for a valid wall plane.
        voxel_size:               Voxel downsample size (0 = disabled).
        vertical_tolerance_deg:   Tolerance from vertical for wall normals.
        horizontal_tolerance_deg: Tolerance from horizontal for floor normals.
    """

    def __init__(
        self,
        min_bin_length: float = 2.0,
        min_bin_width: float = 1.5,
        min_bin_height: float = 0.5,
        floor_distance_threshold: float = 0.05,
        wall_distance_threshold: float = 0.05,
        floor_ransac_n: int = 3,
        floor_ransac_iterations: int = 1000,
        wall_min_points: int = 50,
        voxel_size: float = 0.02,
        vertical_tolerance_deg: float = 15.0,
        horizontal_tolerance_deg: float = 15.0,
    ) -> None:
        self._min_bin_length = min_bin_length
        self._min_bin_width = min_bin_width
        self._min_bin_height = min_bin_height
        self._floor_dist_thresh = floor_distance_threshold
        self._wall_dist_thresh = wall_distance_threshold
        self._floor_ransac_n = floor_ransac_n
        self._floor_ransac_iter = floor_ransac_iterations
        self._wall_min_points = wall_min_points
        self._voxel_size = voxel_size

        self._cos_vertical_tol = float(
            np.cos(np.radians(90.0 - vertical_tolerance_deg))
        )
        self._cos_horizontal_tol = float(
            np.cos(np.radians(horizontal_tolerance_deg))
        )

    def detect(self, points: np.ndarray) -> BinDetectionResult:
        """Run bin detection on a point cloud.

        Args:
            points: Nx3 numpy array of XYZ coordinates.

        Returns:
            BinDetectionResult with detection status and measurements.
        """
        if points is None or len(points) < 20:
            return BinDetectionResult(detected=False)

        pts = np.asarray(points[:, :3], dtype=np.float64)

        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(pts)

        if self._voxel_size > 0:
            cloud = cloud.voxel_down_sample(self._voxel_size)

        cloud_pts = np.asarray(cloud.points)
        if len(cloud_pts) < 20:
            return BinDetectionResult(detected=False)

        # Step 1: Detect the bin floor (lowest horizontal plane)
        floor_result = self._detect_floor(cloud)
        if floor_result is None:
            logger.debug("No floor plane detected")
            return BinDetectionResult(detected=False)

        # Step 2: Separate points above the floor (potential walls + cargo)
        above_floor_mask = self._points_above_plane(
            cloud_pts, floor_result.normal, floor_result.centroid,
            margin=self._floor_dist_thresh,
        )
        above_floor_pts = cloud_pts[above_floor_mask]

        if len(above_floor_pts) < self._wall_min_points:
            logger.debug("Insufficient points above floor: %d", len(above_floor_pts))
            return BinDetectionResult(detected=False)

        # Step 3: Detect vertical wall planes from points above the floor
        walls = self._detect_walls(above_floor_pts)

        # Step 4: Compute bin dimensions from floor extent and wall heights
        dimensions = self._compute_bin_dimensions(
            cloud_pts, floor_result, walls, above_floor_pts
        )

        if dimensions is None:
            return BinDetectionResult(detected=False)

        length, width, height = dimensions

        # Validate against minimum constraints
        if length < self._min_bin_length:
            logger.debug("Bin length %.2f < min %.2f", length, self._min_bin_length)
            return BinDetectionResult(detected=False)
        if width < self._min_bin_width:
            logger.debug("Bin width %.2f < min %.2f", width, self._min_bin_width)
            return BinDetectionResult(detected=False)
        if height < self._min_bin_height:
            logger.debug("Bin height %.2f < min %.2f", height, self._min_bin_height)
            return BinDetectionResult(detected=False)

        volume = length * width * height

        # Step 5: Extract bin points (floor + above-floor within bin bounds)
        bin_points = self._extract_bin_points(
            cloud_pts, floor_result, length, width, height
        )

        return BinDetectionResult(
            detected=True,
            length=length,
            width=width,
            height=height,
            volume=volume,
            floor_centroid=floor_result.centroid.tolist(),
            floor_normal=floor_result.normal.tolist(),
            bin_points=bin_points,
            wall_count=len(walls),
            floor_inlier_count=floor_result.inlier_count,
        )

    def _detect_floor(self, cloud: o3d.geometry.PointCloud) -> Optional[_PlaneResult]:
        """Detect the bin floor as the lowest approximately-horizontal plane."""
        pts = np.asarray(cloud.points)
        if len(pts) < self._floor_ransac_n:
            return None

        plane_model, inlier_indices = cloud.segment_plane(
            distance_threshold=self._floor_dist_thresh,
            ransac_n=self._floor_ransac_n,
            num_iterations=self._floor_ransac_iter,
        )

        if len(inlier_indices) < self._wall_min_points:
            return None

        # plane_model = [a, b, c, d] where ax + by + cz + d = 0
        normal = np.array(plane_model[:3], dtype=np.float64)
        normal_len = np.linalg.norm(normal)
        if normal_len < 1e-9:
            return None
        normal = normal / normal_len

        # Check if the plane is approximately horizontal
        # (normal close to vertical — i.e., |dot(normal, [0,0,1])| > threshold)
        cos_angle = abs(float(np.dot(normal, np.array([0.0, 0.0, 1.0]))))
        if cos_angle < self._cos_horizontal_tol:
            logger.debug(
                "Floor candidate rejected: cos_angle=%.3f < threshold=%.3f",
                cos_angle, self._cos_horizontal_tol,
            )
            return None

        # Ensure normal points upward
        if normal[2] < 0:
            normal = -normal

        inlier_pts = pts[inlier_indices]
        centroid = np.mean(inlier_pts, axis=0)

        return _PlaneResult(
            normal=normal,
            centroid=centroid,
            inlier_indices=np.array(inlier_indices),
            inlier_count=len(inlier_indices),
        )

    def _detect_walls(self, above_floor_pts: np.ndarray) -> List[_PlaneResult]:
        """Detect vertical wall planes from points above the floor.

        Iteratively fits planes via RANSAC and keeps those whose normals
        are approximately horizontal (wall-like).
        """
        walls: List[_PlaneResult] = []
        remaining_pts = above_floor_pts.copy()
        max_wall_iterations = 4  # Max walls to detect (left, right, front, back)

        for _ in range(max_wall_iterations):
            if len(remaining_pts) < self._wall_min_points:
                break

            cloud = o3d.geometry.PointCloud()
            cloud.points = o3d.utility.Vector3dVector(remaining_pts)

            try:
                plane_model, inlier_indices = cloud.segment_plane(
                    distance_threshold=self._wall_dist_thresh,
                    ransac_n=3,
                    num_iterations=500,
                )
            except RuntimeError:
                break

            if len(inlier_indices) < self._wall_min_points:
                break

            normal = np.array(plane_model[:3], dtype=np.float64)
            normal_len = np.linalg.norm(normal)
            if normal_len < 1e-9:
                # Remove these points and continue
                mask = np.ones(len(remaining_pts), dtype=bool)
                mask[inlier_indices] = False
                remaining_pts = remaining_pts[mask]
                continue
            normal = normal / normal_len

            # Check if the plane is approximately vertical
            # (normal close to horizontal — |dot(normal, [0,0,1])| < threshold)
            cos_angle = abs(float(np.dot(normal, np.array([0.0, 0.0, 1.0]))))
            if cos_angle <= self._cos_vertical_tol:
                inlier_pts = remaining_pts[inlier_indices]
                centroid = np.mean(inlier_pts, axis=0)
                walls.append(_PlaneResult(
                    normal=normal,
                    centroid=centroid,
                    inlier_indices=np.array(inlier_indices),
                    inlier_count=len(inlier_indices),
                ))

            # Remove inliers from remaining points for next iteration
            mask = np.ones(len(remaining_pts), dtype=bool)
            mask[inlier_indices] = False
            remaining_pts = remaining_pts[mask]

        return walls

    def _points_above_plane(
        self,
        points: np.ndarray,
        normal: np.ndarray,
        centroid: np.ndarray,
        margin: float = 0.0,
    ) -> np.ndarray:
        """Return boolean mask of points above the plane (in normal direction)."""
        diff = points - centroid
        distances = diff @ normal
        return distances > margin

    def _compute_bin_dimensions(
        self,
        cloud_pts: np.ndarray,
        floor_result: _PlaneResult,
        walls: List[_PlaneResult],
        above_floor_pts: np.ndarray,
    ) -> Optional[Tuple[float, float, float]]:
        """Compute bin length, width, height from detected geometry.

        Strategy:
        - If walls are detected, use wall positions for width and the
          floor extent for length.
        - Height is computed from the max vertical extent of points above
          the floor.
        - Falls back to oriented bounding box of the floor inliers if walls
          are insufficient.
        """
        floor_pts = cloud_pts[floor_result.inlier_indices]

        if len(floor_pts) < 4:
            return None

        # Compute floor extent using PCA on floor inlier XY projection
        floor_xy = floor_pts[:, :2]
        floor_mean = np.mean(floor_xy, axis=0)
        floor_centered = floor_xy - floor_mean

        if len(floor_centered) < 2:
            return None

        cov = np.cov(floor_centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)

        # Sort by eigenvalue descending — first PC is the longest extent
        sort_idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[sort_idx]
        eigenvectors = eigenvectors[:, sort_idx]

        # Project floor points onto principal axes
        projected = floor_centered @ eigenvectors
        length = float(projected[:, 0].max() - projected[:, 0].min())
        width = float(projected[:, 1].max() - projected[:, 1].min())

        # If walls provide better width estimate, use them
        if len(walls) >= 2:
            wall_width = self._width_from_walls(walls)
            if wall_width is not None and wall_width > width * 0.5:
                width = wall_width

        # Height: vertical extent of points above the floor
        if len(above_floor_pts) > 0:
            z_above_floor = above_floor_pts[:, 2] - floor_result.centroid[2]
            height = float(np.percentile(z_above_floor[z_above_floor > 0], 95)) if np.any(z_above_floor > 0) else 0.0
        else:
            height = 0.0

        if length <= 0 or width <= 0 or height <= 0:
            return None

        # Ensure length >= width (length is the longer dimension)
        if width > length:
            length, width = width, length

        return (length, width, height)

    def _width_from_walls(self, walls: List[_PlaneResult]) -> Optional[float]:
        """Estimate bin width from parallel opposing wall planes.

        Finds the pair of walls whose normals are approximately anti-parallel
        and returns the distance between their centroids projected onto the
        average normal direction.
        """
        if len(walls) < 2:
            return None

        best_width: Optional[float] = None

        for i in range(len(walls)):
            for j in range(i + 1, len(walls)):
                dot = float(np.dot(walls[i].normal, walls[j].normal))
                # Anti-parallel walls have dot product close to -1
                if dot < -0.7:
                    avg_normal = walls[i].normal - walls[j].normal
                    avg_normal = avg_normal / (np.linalg.norm(avg_normal) + 1e-9)
                    dist = abs(float(
                        np.dot(walls[i].centroid - walls[j].centroid, avg_normal)
                    ))
                    if best_width is None or dist > best_width:
                        best_width = dist

        return best_width

    def _extract_bin_points(
        self,
        cloud_pts: np.ndarray,
        floor_result: _PlaneResult,
        length: float,
        width: float,
        height: float,
    ) -> np.ndarray:
        """Extract points belonging to the bin region.

        Uses the floor centroid and detected dimensions to define a 3D
        bounding region and returns all points within it.
        """
        centroid = floor_result.centroid

        # Compute oriented bounding box around floor centroid
        # Use a simple axis-aligned approach relative to floor centroid
        half_length = length / 2.0
        half_width = width / 2.0

        # Floor-plane-local coordinates
        diff = cloud_pts - centroid

        # Use PCA axes of floor inliers for orientation
        floor_inlier_pts = cloud_pts[floor_result.inlier_indices]
        floor_xy = floor_inlier_pts[:, :2]
        floor_mean = np.mean(floor_xy, axis=0)
        floor_centered = floor_xy - floor_mean

        if len(floor_centered) < 2:
            return cloud_pts

        cov = np.cov(floor_centered.T)
        _, eigenvectors = np.linalg.eigh(cov)
        sort_idx = np.argsort(np.linalg.eigvalsh(cov))[::-1]
        eigenvectors = eigenvectors[:, sort_idx]

        # Project all points onto floor PCA axes (XY only)
        diff_xy = cloud_pts[:, :2] - floor_mean
        projected = diff_xy @ eigenvectors

        # Height relative to floor
        z_rel = cloud_pts[:, 2] - centroid[2]

        # Bin region mask
        in_length = np.abs(projected[:, 0]) <= half_length * 1.1
        in_width = np.abs(projected[:, 1]) <= half_width * 1.1
        in_height = (z_rel >= -self._floor_dist_thresh) & (z_rel <= height * 1.2)

        bin_mask = in_length & in_width & in_height
        bin_pts = cloud_pts[bin_mask]

        return bin_pts if len(bin_pts) > 0 else cloud_pts
