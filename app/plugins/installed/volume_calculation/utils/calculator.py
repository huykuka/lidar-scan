"""
VolumeCalculator — Open3D-based volume estimation between an empty and a
loaded point cloud.

Pipeline
--------
1. **Outlier removal** — Open3D statistical outlier filter on both clouds.
2. **Ground removal** — Open3D RANSAC plane segmentation; keeps non-ground
   points only.  Skipped when ``remove_ground=False``.
3. **Voxel downsample + normals** — prepares both clouds for ICP.
4. **Multi-scale ICP** — aligns the *empty* cloud to the *loaded* cloud
   using Open3D tensor multi-scale Point-to-Plane ICP (three scales:
   coarse → medium → fine).
5. **Z-delta grid** — projects both aligned clouds onto a shared XY grid,
   interpolates Z surfaces with scipy ``griddata``, computes
   ``ΔZ = Z_loaded − Z_empty``.
6. **Cluster filtering** — morphological opening removes isolated noise
   pixels; the largest connected component is kept.
7. **Volume** — ``Σ(ΔZ_cell × cell_area)`` over the surviving cells.

All Open3D heavy work runs synchronously; the DAG node wraps calls in
``asyncio.to_thread`` to keep the event loop free.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np
import open3d as o3d
# pyrefly: ignore [missing-import]
import open3d.t.pipelines.registration as treg
from scipy.interpolate import griddata
from scipy.ndimage import binary_opening
from scipy.ndimage import label as ndlabel

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class VolumeResult:
    """Output of a single volume calculation run."""

    volume_m3: float                  # estimated volume (m³)
    volume_l: float                   # same in litres
    cell_count: int                   # surviving grid cells
    grid_res: float                   # grid resolution used (m)
    icp_fitness: float                # ICP fitness score
    icp_rmse: float                   # ICP inlier RMSE
    icp_valid: bool                   # True when fitness ≥ min_icp_fitness
    # Flattened arrays of the kept grid region (for downstream visualisation)
    grid_x: np.ndarray = field(default_factory=lambda: np.empty(0))
    grid_y: np.ndarray = field(default_factory=lambda: np.empty(0))
    grid_z: np.ndarray = field(default_factory=lambda: np.empty(0))
    grid_delta: np.ndarray = field(default_factory=lambda: np.empty(0))


# ──────────────────────────────────────────────────────────────────────────────
# Calculator
# ──────────────────────────────────────────────────────────────────────────────


class VolumeCalculator:
    """Compute the volume of material loaded on a surface by comparing two
    aligned point clouds (empty baseline vs loaded state).

    Args:
        voxel_size:                   Voxel size for downsampling before ICP (m).
        outlier_nb_neighbors:         Statistical outlier k-neighbours.
        outlier_std_ratio:            Statistical outlier std-ratio threshold.
        remove_ground:                Run RANSAC ground removal before ICP.
        ground_distance_threshold:    RANSAC inlier distance (m).
        ground_ransac_n:              RANSAC minimum sample size.
        ground_num_iterations:        RANSAC iterations.
        icp_max_correspondence:       ICP max correspondence distance at the
                                      finest scale (voxel_size × 2).
        min_icp_fitness:              Minimum fitness to treat ICP as valid.
                                      Below this, alignment is skipped and
                                      the raw (unaligned) empty is used.
        grid_res:                     XY grid resolution for Z-delta (m).
        delta_threshold:              Minimum ΔZ (m) to count as load.
        morph_open_iterations:        Morphological opening iterations for
                                      noise removal on the 2-D grid.
    """

    def __init__(
        self,
        voxel_size: float = 0.005,
        outlier_nb_neighbors: int = 20,
        outlier_std_ratio: float = 2.0,
        remove_ground: bool = True,
        ground_distance_threshold: float = 0.01,
        ground_ransac_n: int = 3,
        ground_num_iterations: int = 1000,
        icp_max_correspondence: float = 0.05,
        min_icp_fitness: float = 0.3,
        use_icp: bool = True,
        grid_res: float = 0.005,
        delta_threshold: float = 0.02,
        morph_open_iterations: int = 2,
    ) -> None:
        self._voxel_size = voxel_size
        self._outlier_nb = outlier_nb_neighbors
        self._outlier_std = outlier_std_ratio
        self._do_ground = remove_ground
        self._ground_dist = ground_distance_threshold
        self._ground_n = ground_ransac_n
        self._ground_iter = ground_num_iterations
        self._icp_max_corr = icp_max_correspondence
        self._min_fitness = min_icp_fitness
        self._use_icp = use_icp
        self._grid_res = grid_res
        self._delta_threshold = delta_threshold
        self._morph_iter = morph_open_iterations

    # ── Step helpers ──────────────────────────────────────────────────────

    def _to_o3d(self, pts: np.ndarray) -> o3d.geometry.PointCloud:
        """Convert Nx3 (or Nx≥3) numpy array to Open3D PointCloud."""
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(
            np.asarray(pts[:, :3], dtype=np.float64)
        )
        return pcd

    def _remove_outliers(
        self, pcd: o3d.geometry.PointCloud
    ) -> o3d.geometry.PointCloud:
        clean, _ = pcd.remove_statistical_outlier(
            nb_neighbors=self._outlier_nb,
            std_ratio=self._outlier_std,
        )
        removed = len(pcd.points) - len(clean.points)
        logger.debug("Outlier removal: removed %d pts, %d remaining", removed, len(clean.points))
        return clean

    def _remove_ground(
        self, pcd: o3d.geometry.PointCloud
    ) -> o3d.geometry.PointCloud:
        if len(pcd.points) < self._ground_n + 1:
            return pcd
        _, inliers = pcd.segment_plane(
            distance_threshold=self._ground_dist,
            ransac_n=self._ground_n,
            num_iterations=self._ground_iter,
        )
        non_ground = pcd.select_by_index(inliers, invert=True)
        logger.debug(
            "Ground removal: %d ground pts removed, %d pts remaining",
            len(inliers), len(non_ground.points),
        )
        return non_ground

    def _downsample_with_normals(
        self, pcd: o3d.geometry.PointCloud
    ) -> o3d.geometry.PointCloud:
        down = pcd.voxel_down_sample(self._voxel_size)
        down.estimate_normals(
            o3d.geometry.KDTreeSearchParamHybrid(
                radius=self._voxel_size * 2, max_nn=30
            )
        )
        return down

    def _align_icp(
        self,
        empty_down: o3d.geometry.PointCloud,
        loaded_down: o3d.geometry.PointCloud,
    ) -> Tuple[np.ndarray, float, float]:
        """Run multi-scale Point-to-Plane ICP (tensor API).

        Returns:
            transformation (4×4 np.ndarray), fitness, inlier_rmse
        """
        src_t = o3d.t.geometry.PointCloud.from_legacy(empty_down)
        tgt_t = o3d.t.geometry.PointCloud.from_legacy(loaded_down)

        vs = self._voxel_size
        voxel_sizes = o3d.utility.DoubleVector([vs * 4, vs * 2, vs])
        max_corr = o3d.utility.DoubleVector([vs * 8, vs * 4, vs * 2])
        criteria = [
            treg.ICPConvergenceCriteria(relative_fitness=1e-4, relative_rmse=1e-4, max_iteration=20),
            treg.ICPConvergenceCriteria(relative_fitness=1e-5, relative_rmse=1e-5, max_iteration=15),
            treg.ICPConvergenceCriteria(relative_fitness=1e-6, relative_rmse=1e-6, max_iteration=10),
        ]
        estimation = treg.TransformationEstimationPointToPlane()

        result = treg.multi_scale_icp(
            src_t,
            tgt_t,
            voxel_sizes,
            criteria,
            max_corr,
            o3d.core.Tensor.eye(4, o3d.core.Dtype.Float32),
            estimation,
        )

        transformation = result.transformation.numpy()
        fitness = float(result.fitness)
        rmse = float(result.inlier_rmse)
        logger.debug("ICP fitness=%.4f  rmse=%.4f", fitness, rmse)
        return transformation, fitness, rmse

    def _z_delta_volume(
        self,
        empty_aligned: o3d.geometry.PointCloud,
        loaded: o3d.geometry.PointCloud,
    ) -> Tuple[float, float, int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Compute ΔZ volume on a shared XY grid.

        Returns:
            volume_m3, volume_l, cell_count, gx, gy, gz, delta
        """
        pts_e = np.asarray(empty_aligned.points)
        pts_l = np.asarray(loaded.points)

        if len(pts_e) == 0 or len(pts_l) == 0:
            empty_arr = np.empty(0)
            return 0.0, 0.0, 0, empty_arr, empty_arr, empty_arr, empty_arr

        # Shared XY bounds (intersection)
        x_min = max(pts_e[:, 0].min(), pts_l[:, 0].min())
        x_max = min(pts_e[:, 0].max(), pts_l[:, 0].max())
        y_min = max(pts_e[:, 1].min(), pts_l[:, 1].min())
        y_max = min(pts_e[:, 1].max(), pts_l[:, 1].max())

        if x_min >= x_max or y_min >= y_max:
            logger.warning("Empty and loaded clouds have no XY overlap — volume = 0")
            empty_arr = np.empty(0)
            return 0.0, 0.0, 0, empty_arr, empty_arr, empty_arr, empty_arr

        xi = np.arange(x_min, x_max, self._grid_res)
        yi = np.arange(y_min, y_max, self._grid_res)
        gx, gy = np.meshgrid(xi, yi)

        logger.debug(
            "Z-delta grid: %d×%d cells (%.1f cm resolution)",
            len(xi), len(yi), self._grid_res * 100,
        )

        z_empty = griddata(pts_e[:, :2], pts_e[:, 2], (gx, gy), method="linear")
        z_loaded = griddata(pts_l[:, :2], pts_l[:, 2], (gx, gy), method="linear")

        delta = z_loaded - z_empty
        mask = np.isfinite(delta) & (delta > self._delta_threshold)

        # Morphological opening — removes isolated noise pixels
        if self._morph_iter > 0:
            clean_mask = binary_opening(
                mask,
                structure=np.ones((3, 3), dtype=bool),
                iterations=self._morph_iter,
            )
        else:
            clean_mask = mask

        # Largest connected component (8-connectivity)
        labelled, n_components = ndlabel(clean_mask, structure=np.ones((3, 3), dtype=int))
        logger.debug("Connected components after opening: %d", n_components)

        if n_components > 0:
            sizes = np.bincount(labelled.ravel())
            sizes[0] = 0  # ignore background
            best_label = int(sizes.argmax())
            keep_mask = labelled == best_label
        else:
            keep_mask = clean_mask

        gx_flat = gx[keep_mask].ravel()
        gy_flat = gy[keep_mask].ravel()
        gz_flat = z_loaded[keep_mask].ravel()
        delta_flat = delta[keep_mask].ravel()

        cell_area = self._grid_res ** 2
        volume_m3 = float(np.sum(delta_flat) * cell_area)
        volume_l = volume_m3 * 1000.0

        logger.debug(
            "Volume: %d cells  %.6f m³  (%.3f L)",
            len(delta_flat), volume_m3, volume_l,
        )
        return volume_m3, volume_l, len(delta_flat), gx_flat, gy_flat, gz_flat, delta_flat

    # ── Public API ────────────────────────────────────────────────────────

    def calculate(
        self,
        empty_pts: np.ndarray,
        loaded_pts: np.ndarray,
    ) -> VolumeResult:
        """Run the full pipeline and return a :class:`VolumeResult`.

        Args:
            empty_pts:  Nx3 (or Nx≥3) numpy array — the empty baseline scan.
            loaded_pts: Nx3 (or Nx≥3) numpy array — the loaded state scan.

        Returns:
            :class:`VolumeResult` with volume estimates and grid metadata.
        """
        if empty_pts is None or loaded_pts is None:
            raise ValueError("Both empty and loaded point arrays are required")
        if empty_pts.shape[1] < 3 or loaded_pts.shape[1] < 3:
            raise ValueError("Point arrays must have at least 3 columns (XYZ)")

        # 1. Convert to Open3D
        src = self._to_o3d(empty_pts)
        tgt = self._to_o3d(loaded_pts)

        # 2. Outlier removal
        src = self._remove_outliers(src)
        tgt = self._remove_outliers(tgt)

        # 3. Optional ground removal
        if self._do_ground:
            src = self._remove_ground(src)
            tgt = self._remove_ground(tgt)

        # 4. Downsample + normals for ICP
        src_down = self._downsample_with_normals(src)
        tgt_down = self._downsample_with_normals(tgt)

        # 5. Multi-scale ICP — align empty → loaded
        icp_valid = True
        transformation = np.eye(4)
        fitness = 0.0
        rmse = 0.0

        if not self._use_icp:
            logger.debug("ICP disabled — using identity transform")
            icp_valid = False
        elif len(src_down.points) >= 3 and len(tgt_down.points) >= 3:
            try:
                transformation, fitness, rmse = self._align_icp(src_down, tgt_down)
                if fitness < self._min_fitness:
                    logger.warning(
                        "ICP fitness %.4f < min %.4f — using identity transform",
                        fitness, self._min_fitness,
                    )
                    icp_valid = False
                    transformation = np.eye(4)
            except Exception as exc:
                logger.error("ICP failed: %s — using identity transform", exc)
                icp_valid = False
        else:
            logger.warning("Not enough points for ICP — using identity transform")
            icp_valid = False

        # Apply transform to the full (non-downsampled) empty cloud
        empty_aligned = copy.deepcopy(src)
        if icp_valid:
            empty_aligned.transform(transformation)

        # 6. Z-delta volume
        vol_m3, vol_l, cell_count, gx, gy, gz, delta = self._z_delta_volume(
            empty_aligned, tgt
        )

        return VolumeResult(
            volume_m3=vol_m3,
            volume_l=vol_l,
            cell_count=cell_count,
            grid_res=self._grid_res,
            icp_fitness=fitness,
            icp_rmse=rmse,
            icp_valid=icp_valid,
            grid_x=gx,
            grid_y=gy,
            grid_z=gz,
            grid_delta=delta,
        )
