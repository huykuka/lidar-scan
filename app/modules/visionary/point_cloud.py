"""
Vectorized depth-to-point-cloud conversion for SICK Visionary 3D cameras.

Converts depth map, intensity, and confidence data from SICK Visionary cameras
into (N, 14) numpy arrays compatible with the pipeline's standard format.

All coordinates are converted from millimetres (camera native) to metres.

Supports both ToF (Visionary-T Mini) and stereo (Visionary-S, Visionary-B Two)
camera models using the intrinsic camera parameters provided by the device.

Reference: SICK sick_visionary_python_base PointCloud/PointCloud.py
"""
import numpy as np
from typing import Optional

MM_TO_M = 0.001


class ToFProjector:
    """Pre-computes pixel grids and distortion LUTs for ToF cameras.

    Create once per camera configuration, then call :meth:`project` each frame.
    """

    def __init__(
        self,
        width: int,
        height: int,
        fx: float,
        fy: float,
        cx: float,
        cy: float,
        k1: float,
        k2: float,
        f2rc: float,
        cam2world: np.ndarray,
    ) -> None:
        self._height = height
        self._width = width
        self._n_pixels = height * width

        cols = np.arange(width, dtype=np.float32)
        rows = np.arange(height, dtype=np.float32)
        col_grid, row_grid = np.meshgrid(cols, rows)

        xp = (cx - col_grid) / fx
        yp = (cy - row_grid) / fy

        r2 = xp * xp + yp * yp
        r4 = r2 * r2
        k = np.float32(1.0) + np.float32(k1) * r2 + np.float32(k2) * r4

        xd = xp * k
        yd = yp * k
        s0 = np.sqrt(xd * xd + yd * yd + np.float32(1.0))

        # Pre-compute per-pixel direction vectors (flat arrays)
        self._xd_over_s0 = (xd / s0).ravel()
        self._yd_over_s0 = (yd / s0).ravel()
        self._inv_s0 = (np.float32(1.0) / s0).ravel()
        self._f2rc = np.float32(f2rc)

        # Pre-extract cam2world rotation + translation as float32 scalars
        m = cam2world.astype(np.float32)
        self._m00, self._m01, self._m02, self._m03 = m[0, 0], m[0, 1], m[0, 2], m[0, 3]
        self._m10, self._m11, self._m12, self._m13 = m[1, 0], m[1, 1], m[1, 2], m[1, 3]
        self._m20, self._m21, self._m22, self._m23 = m[2, 0], m[2, 1], m[2, 2], m[2, 3]

    def project(
        self,
        dist_data: np.ndarray,
        intensity_data: np.ndarray,
        confidence_data: np.ndarray,
    ) -> np.ndarray:
        """Convert a single ToF frame to (N, 14) point cloud (metres).

        ToF cameras include all pixels (no confidence filter).
        Only zero-distance pixels (no measurement) are excluded.
        """
        dist = dist_data.astype(np.float32).ravel()

        valid = dist > 0
        if not np.any(valid):
            return np.zeros((0, 14), dtype=np.float64)

        dv = dist[valid]
        xd_s0_v = self._xd_over_s0[valid]
        yd_s0_v = self._yd_over_s0[valid]
        inv_s0_v = self._inv_s0[valid]

        xc = xd_s0_v * dv
        yc = yd_s0_v * dv
        zc = inv_s0_v * dv - self._f2rc

        xw = (self._m00 * xc + self._m01 * yc + self._m02 * zc + self._m03) * MM_TO_M
        yw = (self._m10 * xc + self._m11 * yc + self._m12 * zc + self._m13) * MM_TO_M
        zw = (self._m20 * xc + self._m21 * yc + self._m22 * zc + self._m23) * MM_TO_M

        n = int(dv.shape[0])
        out = np.zeros((n, 14), dtype=np.float64)
        out[:, 0] = xw
        out[:, 1] = yw
        out[:, 2] = zw
        out[:, 13] = intensity_data.ravel()[valid]
        return out


class StereoProjector:
    """Pre-computes pixel grids for stereo cameras.

    Create once per camera configuration, then call :meth:`project` each frame.
    """

    def __init__(
        self,
        width: int,
        height: int,
        fx: float,
        fy: float,
        cx: float,
        cy: float,
        cam2world: np.ndarray,
    ) -> None:
        self._height = height
        self._width = width

        cols = np.arange(width, dtype=np.float32)
        rows = np.arange(height, dtype=np.float32)
        col_grid, row_grid = np.meshgrid(cols, rows)

        self._xp = ((col_grid - cx) / fx).ravel()
        self._yp = ((row_grid - cy) / fy).ravel()

        m = cam2world.astype(np.float32)
        self._m00, self._m01, self._m02, self._m03 = m[0, 0], m[0, 1], m[0, 2], m[0, 3]
        self._m10, self._m11, self._m12, self._m13 = m[1, 0], m[1, 1], m[1, 2], m[1, 3]
        self._m20, self._m21, self._m22, self._m23 = m[2, 0], m[2, 1], m[2, 2], m[2, 3]

    def project(
        self,
        dist_data: np.ndarray,
        intensity_data: np.ndarray,
        confidence_data: np.ndarray,
    ) -> np.ndarray:
        """Convert a single stereo frame to (N, 14) point cloud (metres).

        Stereo cameras use confidence to flag invalid pixels (confidence != 0 = invalid).
        Zero-distance pixels are also excluded.
        """
        dist = dist_data.astype(np.float32).ravel()
        conf = np.asarray(confidence_data, dtype=np.uint16).ravel()

        valid = (conf == 0) & (dist > 0)
        if not np.any(valid):
            return np.zeros((0, 14), dtype=np.float64)

        dv = dist[valid]
        xc = self._xp[valid] * dv
        yc = self._yp[valid] * dv

        xw = (self._m00 * xc + self._m01 * yc + self._m02 * dv + self._m03) * MM_TO_M
        yw = (self._m10 * xc + self._m11 * yc + self._m12 * dv + self._m13) * MM_TO_M
        zw = (self._m20 * xc + self._m21 * yc + self._m22 * dv + self._m23) * MM_TO_M

        n = int(dv.shape[0])
        out = np.zeros((n, 14), dtype=np.float64)
        out[:, 0] = xw
        out[:, 1] = yw
        out[:, 2] = zw
        out[:, 13] = intensity_data.ravel()[valid]
        return out


# ---------------------------------------------------------------------------
# Convenience functions (backward-compatible with the original API)
# ---------------------------------------------------------------------------


def depth_to_point_cloud_tof(
    dist_data: np.ndarray,
    intensity_data: np.ndarray,
    confidence_data: np.ndarray,
    width: int,
    height: int,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    k1: float,
    k2: float,
    f2rc: float,
    cam2world: np.ndarray,
) -> np.ndarray:
    """Convert ToF depth map to (N, 14) point cloud array.

    Uses radial distortion correction and cam2world transformation.
    Only zero-distance pixels are excluded (ToF does not use confidence filtering).

    Args:
        dist_data:       Flat distance values (H*W,) in millimetres.
        intensity_data:  Flat intensity values (H*W,).
        confidence_data: Flat confidence values (H*W,); 0 = valid.
        width, height:   Image resolution.
        fx, fy, cx, cy:  Intrinsic camera parameters.
        k1, k2:          Radial distortion coefficients.
        f2rc:            FocalToRayCross offset.
        cam2world:       4x4 camera-to-world transformation matrix.

    Returns:
        (N, 14) float64 array with columns [x, y, z, 0..9, intensity, ...].
        Coordinates are in metres.
    """
    proj = ToFProjector(width, height, fx, fy, cx, cy, k1, k2, f2rc, cam2world)
    return proj.project(dist_data, intensity_data, confidence_data)


def depth_to_point_cloud_stereo(
    dist_data: np.ndarray,
    intensity_data: np.ndarray,
    confidence_data: np.ndarray,
    width: int,
    height: int,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    cam2world: np.ndarray,
) -> np.ndarray:
    """Convert stereo depth map to (N, 14) point cloud array.

    Stereo cameras provide Z-map data directly; no radial distortion model.
    Invalid pixels (confidence != 0 or distance == 0) are excluded.

    Args:
        dist_data:       Flat Z-map values (H*W,) in millimetres.
        intensity_data:  Flat RGBA intensity values (H*W,) packed as uint32.
        confidence_data: Flat confidence values (H*W,); 0 = valid.
        width, height:   Image resolution.
        fx, fy, cx, cy:  Intrinsic camera parameters.
        cam2world:       4x4 camera-to-world transformation matrix.

    Returns:
        (N, 14) float64 array. Coordinates are in metres.
    """
    proj = StereoProjector(width, height, fx, fy, cx, cy, cam2world)
    return proj.project(dist_data, intensity_data, confidence_data)
