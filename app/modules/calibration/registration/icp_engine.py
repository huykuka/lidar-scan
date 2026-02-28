"""
ICP registration engine with two-stage pipeline (Global + ICP).

This module provides fine alignment using Iterative Closest Point algorithm
with optional global registration fallback for poor initial poses.

Uses Open3D legacy API for maximum algorithm support.
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import asyncio
import numpy as np
import open3d as o3d

from .global_registration import GlobalRegistration
from .quality import QualityEvaluator, QualityMetrics


@dataclass
class RegistrationResult:
    """Result from ICP registration"""
    transformation: np.ndarray  # 4x4 transformation matrix
    fitness: float
    rmse: float
    converged: bool
    quality: str  # "excellent", "good", "poor"
    stages_used: List[str]  # ["global", "icp"] or ["icp"]


class ICPEngine:
    """
    Two-stage point cloud registration engine.
    
    Stage 1: Global registration (FPFH + RANSAC) - optional fallback
    Stage 2: ICP refinement (point-to-point or point-to-plane)
    
    Uses Open3D legacy API for broader algorithm support.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize ICP engine.
        
        Args:
            config: Configuration dict with:
                - icp_method: "point_to_plane" or "point_to_point" (default: point_to_plane)
                - icp_threshold: Max correspondence distance (default: 0.02)
                - icp_iterations: Max ICP iterations (default: 50)
                - enable_global_registration: Enable global fallback (default: True)
                - translation_only: Constrain to XYZ translation only, no rotation (default: False)
                - min_fitness: Min fitness for quality gate (default: 0.7)
                - max_rmse: Max RMSE for quality gate (default: 0.05)
        """
        # ICP parameters
        self.method = config.get("icp_method", "point_to_plane")
        self.threshold = config.get("icp_threshold", 0.02)
        self.max_iterations = config.get("icp_iterations", 50)
        self.translation_only = config.get("translation_only", False)
        
        # Global registration
        self.enable_global = config.get("enable_global_registration", True)
        self.global_reg = GlobalRegistration(config) if self.enable_global else None
        
        # Quality evaluation
        self.quality_evaluator = QualityEvaluator(
            min_fitness=config.get("min_fitness", 0.7),
            max_rmse=config.get("max_rmse", 0.05)
        )
    
    async def register(
        self,
        source: np.ndarray,
        target: np.ndarray,
        initial_transform: Optional[np.ndarray] = None
    ) -> RegistrationResult:
        """
        Perform two-stage registration: Global → ICP.
        
        Args:
            source: Source point cloud as (N, 3+) numpy array
            target: Target point cloud as (M, 3+) numpy array
            initial_transform: Initial 4x4 transformation (optional)
            
        Returns:
            RegistrationResult with transformation and quality metrics
        """
        # Run registration off main thread
        def _register():
            stages_used = []
            
            # Convert to Open3D legacy PointCloud
            source_pcd = self._numpy_to_legacy_pcd(source)
            target_pcd = self._numpy_to_legacy_pcd(target)
            
            # Determine initial transformation
            if initial_transform is None:
                init_transform = np.eye(4)
            else:
                init_transform = initial_transform
            
            # Stage 1: Global registration (if needed)
            if self.enable_global and self._needs_global_registration(init_transform):
                global_result = self.global_reg.register(source, target)
                
                if global_result.converged:
                    init_transform = global_result.transformation
                    stages_used.append("global")
            
            # Stage 2: ICP refinement
            # Estimate normals (required for point-to-plane)
            source_pcd.estimate_normals(
                o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30)
            )
            target_pcd.estimate_normals(
                o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30)
            )
            
            # Choose estimation method
            if self.method == "point_to_plane":
                estimation = o3d.pipelines.registration.TransformationEstimationPointToPlane()
            else:
                estimation = o3d.pipelines.registration.TransformationEstimationPointToPoint()
            
            # ICP convergence criteria
            criteria = o3d.pipelines.registration.ICPConvergenceCriteria(
                max_iteration=self.max_iterations
            )
            
            # Run ICP
            icp_result = o3d.pipelines.registration.registration_icp(
                source_pcd,
                target_pcd,
                max_correspondence_distance=self.threshold,
                init=init_transform,
                estimation_method=estimation,
                criteria=criteria
            )
            
            stages_used.append("icp")
            
            # If translation-only mode, extract only translation from ICP result
            # and preserve rotation from initial transform
            final_transform = icp_result.transformation
            if self.translation_only:
                final_transform = self._extract_translation_only(
                    icp_result.transformation,
                    init_transform
                )
            
            # Evaluate quality
            quality_metrics = self.quality_evaluator.evaluate(
                icp_result.fitness,
                icp_result.inlier_rmse
            )
            
            return RegistrationResult(
                transformation=final_transform,
                fitness=icp_result.fitness,
                rmse=icp_result.inlier_rmse,
                converged=icp_result.fitness > 0.3,
                quality=quality_metrics.quality,
                stages_used=stages_used
            )
        
        return await asyncio.to_thread(_register)
    
    def _needs_global_registration(self, transform: np.ndarray) -> bool:
        """
        Check if global registration is needed based on initial transform.
        
        Global registration is needed if the transform is far from identity:
        - Translation > 1.0 meters
        - Rotation > 30 degrees
        
        Args:
            transform: 4x4 transformation matrix
            
        Returns:
            True if global registration should be attempted
        """
        # Check translation distance
        translation = np.linalg.norm(transform[:3, 3])
        if translation > 1.0:
            return True
        
        # Check rotation angle (using trace of rotation matrix)
        # trace(R) = 1 + 2*cos(theta), so theta = arccos((trace(R) - 1) / 2)
        rotation_matrix = transform[:3, :3]
        trace = np.trace(rotation_matrix)
        rotation_angle = np.arccos(np.clip((trace - 1) / 2, -1, 1))
        
        if rotation_angle > np.radians(30):
            return True
        
        return False
    
    def _extract_translation_only(
        self,
        icp_transform: np.ndarray,
        initial_transform: np.ndarray
    ) -> np.ndarray:
        """
        Extract only translation from ICP result, preserve rotation from initial transform.
        
        This is useful when sensors have IMU and already output level point clouds.
        We only need to solve for relative position (X, Y, Z), not orientation.
        
        Args:
            icp_transform: 4x4 transformation from ICP
            initial_transform: 4x4 initial transformation
            
        Returns:
            4x4 transformation with ICP translation + initial rotation
        """
        result = initial_transform.copy()
        # Replace translation with ICP result
        result[:3, 3] = icp_transform[:3, 3]
        return result
    
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
