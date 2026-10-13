"""Find a reference point cloud inside a scene (FPFH+RANSAC, then ICP).

Conventions
-----------
* Units are metres; ``reference_scale`` converts the stored reference.
* ``pose`` is the 4x4 transform mapping reference coordinates into the scene.
* ``fitness`` is the fraction of *reference* points that have a scene point
  within the ICP distance.  For a partially visible object this is < 1 even
  for a perfect match, so ``min_fitness`` has to be tuned per use case.

Two modes:
* global  - FPFH feature matching + RANSAC, then ICP refinement.
* tracking - ICP only, seeded with the previous pose (fast); callers fall back
  to global when the tracked fitness drops below the threshold.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

reg = o3d.pipelines.registration

TRACKING_KEEP_RATIO = 0.8


@dataclass
class MatcherConfig:
    voxel_size: float = 0.05
    min_fitness: float = 0.3
    max_instances: int = 1
    ransac_iterations: int = 100_000
    ransac_confidence: float = 0.999
    icp_iterations: int = 50
    reference_scale: float = 1.0


@dataclass
class Match:
    pose: np.ndarray
    fitness: float
    rmse: float
    stage: str  # "global+icp" | "tracking"
    bbox_min: List[float] = field(default_factory=list)
    bbox_max: List[float] = field(default_factory=list)
    transformed_reference: Optional[np.ndarray] = None  # (M, 3), not serialised

    def to_dict(self) -> Dict[str, Any]:
        t = self.pose[:3, 3]
        # extrinsic xyz Euler angles (roll, pitch, yaw) in degrees
        roll, pitch, yaw = Rotation.from_matrix(self.pose[:3, :3]).as_euler("xyz", degrees=True)
        return {
            "pose": self.pose.tolist(),
            "position": [float(v) for v in t],
            "rotation_deg": {"roll": float(roll), "pitch": float(pitch), "yaw": float(yaw)},
            "fitness": float(self.fitness),
            "rmse": float(self.rmse),
            "stage": self.stage,
            "bbox_min": self.bbox_min,
            "bbox_max": self.bbox_max,
        }


def _to_pcd(points: np.ndarray) -> o3d.geometry.PointCloud:
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.asarray(points[:, :3], dtype=np.float64))
    return pcd


class _Prepared:
    """A downsampled cloud with normals and FPFH features."""

    def __init__(self, points: np.ndarray, voxel: float, features: bool = True) -> None:
        pcd = _to_pcd(points).voxel_down_sample(voxel)
        pcd.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 2.0, max_nn=30))
        self.pcd = pcd
        self.fpfh = (
            reg.compute_fpfh_feature(
                pcd, o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 5.0, max_nn=100)
            )
            if features and len(pcd.points) >= 3
            else None
        )


class Matcher:
    """Holds a prepared reference and finds it in scenes."""

    def __init__(self, reference_points: np.ndarray, config: MatcherConfig) -> None:
        self.cfg = config
        ref = np.asarray(reference_points[:, :3], dtype=np.float64) * config.reference_scale
        # centre the reference so poses describe the object centre, not the CAD origin
        self.ref_origin = ref.mean(axis=0)
        self.ref_full = ref - self.ref_origin
        self.ref = _Prepared(self.ref_full, config.voxel_size)
        self._ref_down = np.asarray(self.ref.pcd.points)

    # ── public ─────────────────────────────────────────────────────────────

    def find(
        self,
        scene: np.ndarray,
        prev_pose: Optional[np.ndarray] = None,
        prev_fitness: Optional[float] = None,
    ) -> List[Match]:
        """Return matches sorted best-first.

        ``prev_pose``/``prev_fitness`` enable tracking.  A tracked result must
        keep ``TRACKING_KEEP_RATIO`` of the previous fitness, otherwise ICP has
        probably slid onto clutter (e.g. the floor) and we search globally.
        """
        cfg = self.cfg
        if len(scene) < 10 or len(self._ref_down) < 3:
            return []

        scene_prep = _Prepared(scene, cfg.voxel_size)
        if len(scene_prep.pcd.points) < 3:
            return []

        matches: List[Match] = []

        # Tracking: single instance seeded from the previous pose.
        if prev_pose is not None and cfg.max_instances == 1:
            m = self._refine(scene_prep, prev_pose, "tracking")
            floor = max(cfg.min_fitness, TRACKING_KEEP_RATIO * (prev_fitness or 0.0))
            if m is not None and m.fitness >= floor:
                return [m]
            # lost — fall through to a full search

        for _ in range(max(1, cfg.max_instances)):
            if len(scene_prep.pcd.points) < len(self._ref_down) * 0.2:
                break  # too little left to contain another instance
            m = self._global(scene_prep)
            if m is None or m.fitness < cfg.min_fitness:
                break
            matches.append(m)
            scene_prep = self._remove_inliers(scene_prep, m)
        return matches

    # ── stages ─────────────────────────────────────────────────────────────

    def _global(self, scene: _Prepared) -> Optional[Match]:
        v = self.cfg.voxel_size
        if scene.fpfh is None or self.ref.fpfh is None:
            return None
        dist = v * 1.5
        ransac = reg.registration_ransac_based_on_feature_matching(
            self.ref.pcd, scene.pcd, self.ref.fpfh, scene.fpfh,
            True,  # mutual_filter
            dist,
            reg.TransformationEstimationPointToPoint(False),
            3,
            [
                reg.CorrespondenceCheckerBasedOnEdgeLength(0.9),
                reg.CorrespondenceCheckerBasedOnDistance(dist),
            ],
            reg.RANSACConvergenceCriteria(self.cfg.ransac_iterations, self.cfg.ransac_confidence),
        )
        if len(ransac.correspondence_set) == 0:
            return None
        return self._refine(scene, ransac.transformation, "global+icp")

    def _refine(self, scene: _Prepared, init: np.ndarray, stage: str) -> Optional[Match]:
        res = reg.registration_icp(
            self.ref.pcd, scene.pcd,
            self.cfg.voxel_size * 1.5,
            np.asarray(init, dtype=np.float64),
            reg.TransformationEstimationPointToPlane(),
            reg.ICPConvergenceCriteria(max_iteration=self.cfg.icp_iterations),
        )
        if res.fitness <= 0:
            return None
        pose = np.asarray(res.transformation)
        moved = (self.ref_full @ pose[:3, :3].T) + pose[:3, 3]
        return Match(
            pose=pose, fitness=res.fitness, rmse=res.inlier_rmse, stage=stage,
            bbox_min=[float(v) for v in moved.min(axis=0)],
            bbox_max=[float(v) for v in moved.max(axis=0)],
            transformed_reference=moved,
        )

    def _remove_inliers(self, scene: _Prepared, match: Match) -> _Prepared:
        """Drop scene points explained by *match* so the next pass finds another instance."""
        pts = np.asarray(scene.pcd.points)
        tree = cKDTree(match.transformed_reference)
        d, _ = tree.query(pts, distance_upper_bound=self.cfg.voxel_size * 2.0)
        keep = pts[~np.isfinite(d)]
        if len(keep) < 3:
            return _Prepared(np.zeros((0, 3)), self.cfg.voxel_size, features=False)
        # features depend on the neighbourhood, so recompute on what is left
        out = _Prepared.__new__(_Prepared)
        pcd = _to_pcd(keep)
        pcd.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(
            radius=self.cfg.voxel_size * 2.0, max_nn=30))
        out.pcd = pcd
        out.fpfh = reg.compute_fpfh_feature(
            pcd, o3d.geometry.KDTreeSearchParamHybrid(radius=self.cfg.voxel_size * 5.0, max_nn=100))
        return out


def points_near_matches(scene: np.ndarray, matches: List[Match], radius: float) -> np.ndarray:
    """Return the rows of *scene* lying within *radius* of any matched reference."""
    if not matches:
        return scene[:0]
    ref_pts = np.concatenate([m.transformed_reference for m in matches if m.transformed_reference is not None])
    d, _ = cKDTree(ref_pts).query(scene[:, :3], distance_upper_bound=radius)
    return scene[np.isfinite(d)]
