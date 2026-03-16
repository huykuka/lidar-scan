"""
Global registration using FPFH features and RANSAC or Fast Global Registration (FGR).

This module provides coarse alignment for point clouds when initial poses are rough.
Uses Open3D's legacy API for FPFH feature computation and RANSAC/FGR matching.
"""
from dataclasses import dataclass
from typing import Dict, Any
import numpy as np
import open3d as o3d


@dataclass
class GlobalResult:
    """Result from global registration"""
    transformation: np.ndarray  # 4x4 transformation matrix
    fitness: float
    num_correspondences: int
    converged: bool
    method: str = "ransac"  # "ransac" or "fgr"


class GlobalRegistration:
    """
    Performs coarse global registration using FPFH features and RANSAC or FGR.
    
    This provides a rough initial alignment when sensor poses are far off
    (>1m translation or >30° rotation from identity).
    
    Supports two global registration strategies:
    - RANSAC (default): Robust but slower. Better for noisy data.
    - FGR (Fast Global Registration): Faster and often more accurate.
      Controlled by use_fast_global_registration config flag.
    
    Uses Open3D legacy API for broader algorithm support.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize global registration.
        
        Args:
            config: Configuration dict with:
                - global_voxel_size: Voxel size for downsampling (default: 0.05)
                - feature_radius: Radius for FPFH feature computation (default: 0.1)
                - ransac_threshold: RANSAC distance threshold (default: 0.075)
                - ransac_iterations: Max RANSAC iterations (default: 100000)
                - use_fast_global_registration: Use FGR instead of RANSAC (default: False)
        """
        self.voxel_size = config.get("global_voxel_size", 0.05)
        self.feature_radius = config.get("feature_radius", self.voxel_size * 2)
        self.ransac_threshold = config.get("ransac_threshold", 0.075)
        self.max_iterations = config.get("ransac_iterations", 100000)
        self.use_fgr = config.get("use_fast_global_registration", False)
    
    def register(self, source: np.ndarray, target: np.ndarray) -> GlobalResult:
        """
        Perform global registration using FPFH + RANSAC or FGR.

        Selects the algorithm based on the ``use_fast_global_registration`` flag
        set in the constructor config.  Both paths share the same downsampling,
        normal estimation, and FPFH feature computation steps.

        Args:
            source: Source point cloud as (N, 3+) numpy array
            target: Target point cloud as (M, 3+) numpy array

        Returns:
            GlobalResult with coarse transformation matrix and ``method`` set to
            ``"ransac"`` or ``"fgr"`` accordingly.
        """
        # Convert to Open3D legacy PointCloud
        source_pcd = self._numpy_to_legacy_pcd(source)
        target_pcd = self._numpy_to_legacy_pcd(target)
        
        # Downsample for speed
        source_down = source_pcd.voxel_down_sample(self.voxel_size)
        target_down = target_pcd.voxel_down_sample(self.voxel_size)

        # Estimate normals (required for FPFH)
        source_down.estimate_normals(
            o3d.geometry.KDTreeSearchParamHybrid(
                radius=self.voxel_size * 2,
                max_nn=30
            )
        )
        target_down.estimate_normals(
            o3d.geometry.KDTreeSearchParamHybrid(
                radius=self.voxel_size * 2,
                max_nn=30
            )
        )
        
        # Compute FPFH features
        source_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
            source_down,
            o3d.geometry.KDTreeSearchParamHybrid(
                radius=self.feature_radius,
                max_nn=100
            )
        )
        target_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
            target_down,
            o3d.geometry.KDTreeSearchParamHybrid(
                radius=self.feature_radius,
                max_nn=100
            )
        )
        
        if self.use_fgr:
            # Fast Global Registration — faster and often more accurate than RANSAC
            result = o3d.pipelines.registration.registration_fgr_based_on_feature_matching(
                source_down,
                target_down,
                source_fpfh,
                target_fpfh,
                o3d.pipelines.registration.FastGlobalRegistrationOption(
                    maximum_correspondence_distance=self.voxel_size * 0.5
                )
            )
            method = "fgr"
        else:
            # RANSAC-based global registration — robust for noisy data
            result = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
                source_down,
                target_down,
                source_fpfh,
                target_fpfh,
                mutual_filter=True,
                max_correspondence_distance=self.ransac_threshold,
                estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(False),
                ransac_n=3,
                checkers=[
                    o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
                    o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(self.ransac_threshold)
                ],
                criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(
                    max_iteration=self.max_iterations,
                    confidence=0.999
                )
            )
            method = "ransac"

        return GlobalResult(
            transformation=result.transformation,
            fitness=result.fitness,
            num_correspondences=len(result.correspondence_set),
            converged=result.fitness > 0.3,  # Minimum threshold for success
            method=method
        )
    
    def _numpy_to_legacy_pcd(self, points: np.ndarray) -> o3d.geometry.PointCloud:
        """
        Convert numpy array to Open3D legacy PointCloud.
        
        Args:
            points: (N, 3+) numpy array (only first 3 columns used for XYZ)
            
        Returns:
            Open3D legacy PointCloud
        """
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points[:, :3].astype(np.float64))
        return pcd
