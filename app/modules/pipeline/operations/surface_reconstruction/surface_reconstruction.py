"""
SurfaceReconstruction — Pipeline Operation (Dispatcher)
========================================================

Entry point for the surface reconstruction pipeline operation.
Dispatches to the appropriate algorithm class based on configuration:

  alpha_shape    → AlphaShapeReconstruction
  ball_pivoting  → BallPivotingReconstruction
  poisson        → PoissonReconstruction

The SurfaceReconstruction class inherits from PipelineOperation and handles:
  - Input validation and normalisation (tensor/legacy PointCloud)
  - Normal estimation when required (BPA and Poisson need normals)
  - Algorithm resolution and delegation
  - Mesh-to-pointcloud conversion for downstream DAG consumption
  - Metadata assembly (status, counts, timing)
  - Fail-safe error handling (never raises)
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

import open3d as o3d

from ...base import PipelineOperation
from .reconstruction_base import (
    MIN_INPUT_POINTS,
    _VALID_ALGORITHMS,
    AlphaShapeParams,
    BallPivotingParams,
    PoissonReconstructionParams,
    ReconstructionAlgorithmBase,
    ReconstructionStatus,
    _ensure_normals,
    _get_count,
    _to_legacy,
)
from .alpha_shape import AlphaShapeReconstruction
from .ball_pivoting import BallPivotingReconstruction
from .poisson import PoissonReconstruction

logger = logging.getLogger(__name__)

_ALGORITHM_MAP: Dict[str, type] = {
    "alpha_shape": AlphaShapeReconstruction,
    "ball_pivoting": BallPivotingReconstruction,
    "poisson": PoissonReconstruction,
}


class SurfaceReconstruction(PipelineOperation):
    """
    Surface reconstruction operation — converts point clouds to triangle meshes.

    The reconstructed mesh is sampled back into a point cloud so downstream DAG
    nodes continue to receive the standard (N, 14) array format.

    Args:
        algorithm:         Algorithm key string (default 'poisson').
        sample_points:     Resample mesh to N points. 0 = use mesh vertices.
        estimate_normals:  Estimate normals on input if missing.
        normal_radius:     Search radius for normal estimation.
        normal_max_nn:     Max neighbours for normal estimation.
        alpha_shape_params:     AlphaShapeParams or dict.
        ball_pivoting_params:   BallPivotingParams or dict.
        poisson_params:         PoissonReconstructionParams or dict.
    """

    def __init__(
        self,
        algorithm: str = "poisson",
        sample_points: int = 0,
        estimate_normals: bool = True,
        normal_radius: float = 0.1,
        normal_max_nn: int = 30,
        alpha_shape_params: Optional[Any] = None,
        ball_pivoting_params: Optional[Any] = None,
        poisson_params: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        if algorithm not in _VALID_ALGORITHMS:
            raise ValueError(
                f"algorithm must be one of {sorted(_VALID_ALGORITHMS)}, got '{algorithm}'"
            )

        self.algorithm: str = algorithm
        self.sample_points: int = int(sample_points)
        self.estimate_normals: bool = bool(estimate_normals)
        self.normal_radius: float = float(normal_radius)
        self.normal_max_nn: int = int(normal_max_nn)

        self.alpha_shape_params: Optional[AlphaShapeParams] = self._coerce_params(
            alpha_shape_params, AlphaShapeParams
        )
        self.ball_pivoting_params: Optional[BallPivotingParams] = self._coerce_params(
            ball_pivoting_params, BallPivotingParams
        )
        self.poisson_params: Optional[PoissonReconstructionParams] = self._coerce_params(
            poisson_params, PoissonReconstructionParams
        )

        logger.debug(
            "SurfaceReconstruction: algorithm=%s, sample_points=%d",
            algorithm, sample_points,
        )

    # ─── Public API ──────────────────────────────────────────────────────────

    def apply(self, pcd: Any) -> Tuple[Any, Dict[str, Any]]:
        """
        Reconstruct a surface from the input point cloud.

        Returns:
            Tuple of (output point cloud, metadata dict).
        """
        t0 = time.perf_counter()
        n_in = _get_count(pcd)

        if n_in < MIN_INPUT_POINTS:
            return pcd, self._build_meta(ReconstructionStatus.SKIPPED, n_in, 0, 0, 0, t0)

        try:
            # Convert to legacy for Open3D surface reconstruction APIs
            legacy_pcd = _to_legacy(pcd)

            # Estimate normals if requested (BPA and Poisson require them)
            if self.estimate_normals:
                legacy_pcd = _ensure_normals(
                    legacy_pcd,
                    radius=self.normal_radius,
                    max_nn=self.normal_max_nn,
                )

            # Resolve and run the algorithm
            algo = self._build_algorithm()
            mesh = algo.reconstruct(legacy_pcd)

            n_verts = len(mesh.vertices)
            n_tris = len(mesh.triangles)

            # Convert mesh back to point cloud for downstream consumption
            if self.sample_points > 0 and n_tris > 0:
                out_pcd = mesh.sample_points_poisson_disk(self.sample_points)
            else:
                out_pcd = o3d.geometry.PointCloud()
                out_pcd.points = mesh.vertices
                if mesh.has_vertex_normals():
                    out_pcd.normals = mesh.vertex_normals
                if mesh.has_vertex_colors():
                    out_pcd.colors = mesh.vertex_colors

            n_out = len(out_pcd.points)

            # Convert back to tensor if the input was tensor-based
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                out_pcd = o3d.t.geometry.PointCloud.from_legacy(out_pcd)

            return out_pcd, self._build_meta(
                ReconstructionStatus.SUCCESS, n_in, n_out, n_verts, n_tris, t0
            )

        except Exception as exc:
            logger.error("SurfaceReconstruction failed: %s", exc, exc_info=True)
            return pcd, self._build_meta(
                ReconstructionStatus.ERROR, n_in, n_in, 0, 0, t0, error=str(exc)
            )

    # ─── Internal ────────────────────────────────────────────────────────────

    def _build_algorithm(self) -> ReconstructionAlgorithmBase:
        """Instantiate the selected algorithm with its params."""
        params_map = {
            "alpha_shape": self.alpha_shape_params,
            "ball_pivoting": self.ball_pivoting_params,
            "poisson": self.poisson_params,
        }
        params = params_map.get(self.algorithm)
        algo_cls = _ALGORITHM_MAP[self.algorithm]
        return algo_cls(params=params)

    @staticmethod
    def _coerce_params(raw: Any, model_cls: type) -> Optional[Any]:
        """Coerce a dict to the typed Pydantic model, or return as-is."""
        if raw is None:
            return None
        if isinstance(raw, model_cls):
            return raw
        if isinstance(raw, dict):
            return model_cls(**raw)
        return raw

    def _build_meta(
        self,
        status: ReconstructionStatus,
        n_in: int,
        n_out: int,
        n_verts: int,
        n_tris: int,
        t0: float,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "status": status.value,
            "algorithm": self.algorithm,
            "input_points": n_in,
            "output_points": n_out,
            "mesh_vertices": n_verts,
            "mesh_triangles": n_tris,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
        if error:
            meta["error"] = error
        return meta
