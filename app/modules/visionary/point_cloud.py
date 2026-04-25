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
        cols = np.arange(width, dtype=np.float64)
        rows = np.arange(height, dtype=np.float64)
        col_grid, row_grid = np.meshgrid(cols, rows)

        xp = (cx - col_grid) / fx
        yp = (cy - row_grid) / fy

        r2 = xp * xp + yp * yp
        r4 = r2 * r2
        k = 1.0 + k1 * r2 + k2 * r4

        self._xd = xp * k
        self._yd = yp * k
        self._s0 = np.sqrt(self._xd * self._xd + self._yd * self._yd + 1.0)
        self._f2rc = f2rc
        self._cam2world = cam2world
        self._height = height
        self._width = width

    def project(
        self,
        dist_data: np.ndarray,
        intensity_data: np.ndarray,
        confidence_data: np.ndarray,
    ) -> np.ndarray:
        """Convert a single ToF frame to (N, 14) point cloud (metres)."""
        dist = np.asarray(dist_data, dtype=np.float64).reshape(self._height, self._width)
        conf = np.asarray(confidence_data, dtype=np.uint16).reshape(self._height, self._width)
        ints = np.asarray(intensity_data, dtype=np.float64).reshape(self._height, self._width)

        xc = self._xd * dist / self._s0
        yc = self._yd * dist / self._s0
        zc = dist / self._s0 - self._f2rc

        m = self._cam2world
        xw = m[0, 0] * xc + m[0, 1] * yc + m[0, 2] * zc + m[0, 3]
        yw = m[1, 0] * xc + m[1, 1] * yc + m[1, 2] * zc + m[1, 3]
        zw = m[2, 0] * xc + m[2, 1] * yc + m[2, 2] * zc + m[2, 3]

        valid = conf == 0
        xw_valid = xw[valid] * MM_TO_M
        yw_valid = yw[valid] * MM_TO_M
        zw_valid = zw[valid] * MM_TO_M
        ints_valid = ints[valid]

        n = int(xw_valid.shape[0])
        if n == 0:
            return np.zeros((0, 14), dtype=np.float64)

        out = np.zeros((n, 14), dtype=np.float64)
        out[:, 0] = xw_valid
        out[:, 1] = yw_valid
        out[:, 2] = zw_valid
        out[:, 13] = ints_valid
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
        cols = np.arange(width, dtype=np.float64)
        rows = np.arange(height, dtype=np.float64)
        col_grid, row_grid = np.meshgrid(cols, rows)

        self._xp = (col_grid - cx) / fx
        self._yp = (row_grid - cy) / fy
        self._cam2world = cam2world
        self._height = height
        self._width = width

    def project(
        self,
        dist_data: np.ndarray,
        intensity_data: np.ndarray,
        confidence_data: np.ndarray,
    ) -> np.ndarray:
        """Convert a single stereo frame to (N, 14) point cloud (metres)."""
        dist = np.asarray(dist_data, dtype=np.float64).reshape(self._height, self._width)
        conf = np.asarray(confidence_data, dtype=np.uint16).reshape(self._height, self._width)
        ints = np.asarray(intensity_data, dtype=np.float64).reshape(self._height, self._width)

        zc = dist
        xc = self._xp * zc
        yc = self._yp * zc

        m = self._cam2world
        xw = m[0, 0] * xc + m[0, 1] * yc + m[0, 2] * zc + m[0, 3]
        yw = m[1, 0] * xc + m[1, 1] * yc + m[1, 2] * zc + m[1, 3]
        zw = m[2, 0] * xc + m[2, 1] * yc + m[2, 2] * zc + m[2, 3]

        valid = conf == 0
        xw_valid = xw[valid] * MM_TO_M
        yw_valid = yw[valid] * MM_TO_M
        zw_valid = zw[valid] * MM_TO_M
        ints_valid = ints[valid]

        n = int(xw_valid.shape[0])
        if n == 0:
            return np.zeros((0, 14), dtype=np.float64)

        out = np.zeros((n, 14), dtype=np.float64)
        out[:, 0] = xw_valid
        out[:, 1] = yw_valid
        out[:, 2] = zw_valid
        out[:, 13] = ints_valid
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
    Invalid pixels (confidence != 0) are excluded.

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
    Invalid pixels (confidence != 0) are excluded.

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
