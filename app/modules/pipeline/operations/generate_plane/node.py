"""
GeneratePlane — Pipeline Operation
===================================

Generates a planar mesh from a segmented point cloud.

NUMPY_ONLY: apply() receives a raw (N, M) numpy array and returns a
(V, M) array of mesh vertex positions. No Open3D allocation or thread hop
for the common case. The full mesh topology is embedded in metadata as
plain numpy arrays (vertices, triangles) so downstream mesh-aware nodes
can consume it without depending on Open3D types.

Design notes
------------
- ``plane_model`` can be provided explicitly; if absent a fast least-squares
  plane fit is used (no RANSAC, no Open3D — sub-millisecond).
- The TriangleMesh is stored in metadata["vertices"] / metadata["triangles"]
  as numpy arrays.  If Open3D is available, metadata["mesh"] additionally
  holds an o3d.t.geometry.TriangleMesh for mesh-aware downstream nodes.
- Square mode: centred grid at origin, Z-axis normal.
- Boundary mode: convex-hull-fitted grid back-projected onto the plane.

Parameters
----------
mode : str
    "square" or "boundary".
size : float
    Side length in metres (square mode only). Default 1.0.
voxel_size : float
    Vertex grid spacing in metres. Default 0.05.
plane_model : Optional[List[float]]
    [a, b, c, d] plane coefficients (ax+by+cz+d=0). If None, fitted via
    least-squares from the input points.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.spatial import ConvexHull, Delaunay, QhullError

from ...base import PipelineOperation

logger = logging.getLogger(__name__)

MAX_VERTICES: int = 1_000_000
MIN_POINTS: int = 3
_VALID_MODES = {"square", "boundary"}


def _fit_plane_lstsq(pts: np.ndarray) -> np.ndarray:
    """Fit a plane ax+by+cz+d=0 to pts (N,3) via SVD — sub-millisecond.

    Returns a normalised [a, b, c, d] float64 array.
    """
    centroid = pts.mean(axis=0)
    _, _, Vt = np.linalg.svd(pts - centroid)
    normal = Vt[-1]                      # smallest singular vector
    normal = normal / np.linalg.norm(normal)
    d = -float(normal @ centroid)
    return np.array([*normal, d], dtype=np.float64)


class GeneratePlane(PipelineOperation):
    """
    Generates a planar mesh from a segmented point cloud.

    NUMPY_ONLY: operates directly on the (N, M) float32 array.
    Vertex positions are output as a (V, M) array so the DAG keeps flowing.

    Args:
        mode:        "square" | "boundary"
        size:        Side length in metres (square mode). Default 1.0.
        voxel_size:  Vertex grid spacing in metres. Default 0.05.
        plane_model: Optional [a,b,c,d]. If None, fitted via least-squares.
    """

    NUMPY_ONLY = True

    def __init__(
        self,
        mode: str = "square",
        size: float = 1.0,
        voxel_size: float = 0.05,
        plane_model: Optional[List[float]] = None,
    ) -> None:
        if mode not in _VALID_MODES:
            raise ValueError(f"mode must be 'square' or 'boundary', got '{mode}'")
        if float(voxel_size) <= 0:
            raise ValueError("voxel_size must be > 0")

        self.mode = mode
        self.size = float(size)
        self.voxel_size = float(voxel_size)
        self.plane_model: Optional[List[float]] = (
            [float(v) for v in plane_model] if plane_model is not None else None
        )

    # ─── Public API ───────────────────────────────────────────────────────────

    def apply(self, pts: Any) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Generate a planar mesh from input points.

        Accepts either a raw (N, M) numpy array (NUMPY_ONLY fast path) or an
        Open3D PointCloud (legacy callers / tests).

        Returns:
            vertex_pts: (V, M) numpy array — vertex XYZ packed into the same
                        column layout as the pipeline array.
            metadata: {
                "vertices":       np.ndarray (V, 3) float32,
                "triangles":      np.ndarray (T, 3) int32,
                "mesh":           o3d.t.geometry.TriangleMesh (if open3d available),
                "vertex_count":   int,
                "triangle_count": int,
                "area":           float,
                "plane_model":    List[float],
                "mode":           str,
                "voxel_size":     float,
            }
        """
        # Normalise input — accept numpy array or Open3D PCD
        if isinstance(pts, np.ndarray):
            n_cols = pts.shape[1] if pts.ndim > 1 else 3
        else:
            # Open3D PCD (legacy callers / unit tests)
            try:
                import open3d as o3d
                if isinstance(pts, o3d.t.geometry.PointCloud):
                    raw = pts.point.positions.cpu().numpy().astype(np.float32)
                elif isinstance(pts, o3d.geometry.PointCloud):
                    raw = np.asarray(pts.points, dtype=np.float32)
                else:
                    raise TypeError(f"Unsupported input type: {type(pts)}")
            except ImportError:
                raise TypeError(f"Unsupported input type: {type(pts)}")
            pts = np.zeros((raw.shape[0], 14), dtype=np.float32)
            pts[:, :3] = raw
            n_cols = 14
        if pts.shape[0] < MIN_POINTS:
            raise ValueError(
                f"Insufficient points for plane generation (minimum {MIN_POINTS})"
            )

        # Resolve plane model
        if self.plane_model is not None:
            plane = np.array(self.plane_model, dtype=np.float64)
        else:
            plane = _fit_plane_lstsq(pts[:, :3].astype(np.float64))

        normal_len = math.sqrt(float(plane[0])**2 + float(plane[1])**2 + float(plane[2])**2)
        if normal_len < 1e-6:
            raise ValueError("Invalid plane model: degenerate normal vector")

        # Generate vertices and triangles
        if self.mode == "square":
            vertices, triangles = self._generate_square(plane)
            area = float(self.size * self.size)
            out_plane_model = [0.0, 0.0, 1.0, 0.0]
        else:
            vertices, triangles = self._generate_boundary(pts[:, :3].astype(np.float64), plane)
            area = self._mesh_area(vertices, triangles)
            out_plane_model = plane.tolist()

        # Build output array: vertices as (V, M) with same column count as input
        vertex_pts = np.zeros((vertices.shape[0], n_cols), dtype=pts.dtype)
        vertex_pts[:, :3] = vertices.astype(pts.dtype)

        metadata: Dict[str, Any] = {
            "vertices": vertices.astype(np.float32),
            "triangles": triangles,
            "vertex_count": int(vertices.shape[0]),
            "triangle_count": int(triangles.shape[0]),
            "area": float(area),
            "plane_model": out_plane_model,
            "mode": self.mode,
            "voxel_size": self.voxel_size,
        }

        # Attach Open3D mesh object if available (optional, for mesh-aware nodes)
        try:
            import open3d as o3d
            mesh = o3d.t.geometry.TriangleMesh()
            mesh.vertex.positions = o3d.core.Tensor(vertices.astype(np.float32))
            mesh.triangle.indices = o3d.core.Tensor(triangles.astype(np.int32))
            metadata["mesh"] = mesh
        except Exception:
            pass

        logger.debug(
            "GeneratePlane[%s]: %d vertices, %d triangles, area=%.3f",
            self.mode, metadata["vertex_count"], metadata["triangle_count"], area,
        )
        return vertex_pts, metadata

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _generate_square(self, plane_model: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Uniform grid mesh centred at origin, Z-up normal."""
        if self.size <= 0:
            raise ValueError("size must be > 0")

        n_steps = math.ceil(self.size / self.voxel_size)
        if n_steps * n_steps > MAX_VERTICES:
            raise ValueError(
                f"Mesh would have ~{n_steps*n_steps:,} vertices (limit 1,000,000). "
                f"Increase voxel_size."
            )

        coords = np.linspace(-self.size / 2.0, self.size / 2.0, n_steps, dtype=np.float64)
        XX, YY = np.meshgrid(coords, coords)
        vertices = np.column_stack([XX.ravel(), YY.ravel(), np.zeros(n_steps * n_steps)])

        n_cells = (n_steps - 1) ** 2
        triangles = np.empty((n_cells * 2, 3), dtype=np.int32)
        row_idx = np.arange(n_steps - 1, dtype=np.int32)
        col_idx = np.arange(n_steps - 1, dtype=np.int32)
        rows, cols = np.meshgrid(row_idx, col_idx, indexing="ij")
        rows, cols = rows.ravel(), cols.ravel()
        tl = rows * n_steps + cols
        tr = tl + 1
        bl = tl + n_steps
        br = bl + 1
        triangles[0::2] = np.column_stack([tl, bl, tr])
        triangles[1::2] = np.column_stack([tr, bl, br])
        return vertices, triangles

    def _generate_boundary(
        self, pts_3d: np.ndarray, plane_model: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Convex-hull-fitted grid back-projected onto the plane."""
        a, b, c, d = plane_model
        normal_len = math.sqrt(a**2 + b**2 + c**2)
        n_hat = np.array([a, b, c], dtype=np.float64) / normal_len

        # Orthonormal basis {u, v} on the plane
        world_z = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        cross = np.cross(n_hat, world_z)
        if np.linalg.norm(cross) > 1e-6:
            u = cross / np.linalg.norm(cross)
        else:
            cross = np.cross(n_hat, np.array([1.0, 0.0, 0.0]))
            u = cross / np.linalg.norm(cross)
        v = np.cross(n_hat, u)
        v /= np.linalg.norm(v)

        P0 = (-d / (a**2 + b**2 + c**2)) * np.array([a, b, c], dtype=np.float64)

        # Project 3D → 2D
        X_local = pts_3d - P0
        uv_2d = np.column_stack([X_local @ u, X_local @ v])

        try:
            hull = ConvexHull(uv_2d)
        except QhullError:
            raise ValueError("Cannot compute convex hull: projected points are colinear")

        hull_verts_2d = uv_2d[hull.vertices]
        u_min, u_max = float(uv_2d[:, 0].min()), float(uv_2d[:, 0].max())
        v_min, v_max = float(uv_2d[:, 1].min()), float(uv_2d[:, 1].max())

        if (u_max - u_min) < self.voxel_size or (v_max - v_min) < self.voxel_size:
            raise ValueError("Cannot compute convex hull: projected points are colinear")

        n_u = math.ceil((u_max - u_min) / self.voxel_size) + 1
        n_v = math.ceil((v_max - v_min) / self.voxel_size) + 1
        if n_u * n_v > MAX_VERTICES:
            raise ValueError(
                f"Mesh would have ~{n_u*n_v:,} vertices (limit 1,000,000). "
                f"Increase voxel_size."
            )

        grid_us = np.linspace(u_min, u_max, n_u, dtype=np.float64)
        grid_vs = np.linspace(v_min, v_max, n_v, dtype=np.float64)
        GU, GV = np.meshgrid(grid_us, grid_vs)
        grid_2d = np.column_stack([GU.ravel(), GV.ravel()])

        hull_delaunay = Delaunay(hull_verts_2d)
        inside_mask = hull_delaunay.find_simplex(grid_2d) >= 0

        if inside_mask.sum() < 3:
            raise ValueError("Cannot compute convex hull: projected points are colinear")

        new_idx = np.full(n_u * n_v, -1, dtype=np.int32)
        interior_flat = np.where(inside_mask)[0]
        new_idx[interior_flat] = np.arange(len(interior_flat), dtype=np.int32)

        interior_2d = grid_2d[interior_flat]
        interior_3d = P0 + interior_2d[:, 0:1] * u + interior_2d[:, 1:2] * v

        # Grid-based triangulation — O(N), CCW winding
        row_idx = np.arange(n_v - 1, dtype=np.int32)
        col_idx = np.arange(n_u - 1, dtype=np.int32)
        rows, cols = np.meshgrid(row_idx, col_idx, indexing="ij")
        rows, cols = rows.ravel(), cols.ravel()
        flat_tl = rows * n_u + cols
        idx_tl = new_idx[flat_tl]
        idx_tr = new_idx[flat_tl + 1]
        idx_bl = new_idx[flat_tl + n_u]
        idx_br = new_idx[flat_tl + n_u + 1]

        valid = (idx_tl >= 0) & (idx_tr >= 0) & (idx_bl >= 0) & (idx_br >= 0)
        if valid.sum() == 0:
            raise ValueError("Cannot compute convex hull: projected points are colinear")

        tl, tr, bl, br = idx_tl[valid], idx_tr[valid], idx_bl[valid], idx_br[valid]
        triangles = np.empty((valid.sum() * 2, 3), dtype=np.int32)
        triangles[0::2] = np.column_stack([tl, bl, tr])
        triangles[1::2] = np.column_stack([tr, bl, br])
        return interior_3d, triangles

    @staticmethod
    def _mesh_area(vertices: np.ndarray, triangles: np.ndarray) -> float:
        """Compute total surface area from vertex/triangle arrays."""
        try:
            v0 = vertices[triangles[:, 0]]
            v1 = vertices[triangles[:, 1]]
            v2 = vertices[triangles[:, 2]]
            cross = np.cross(v1 - v0, v2 - v0)
            return float(0.5 * np.linalg.norm(cross, axis=1).sum())
        except Exception:
            return 0.0
