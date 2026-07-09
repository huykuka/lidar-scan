"""
RangeImage (BEV) — Pipeline Operation
========================================

Converts a 3D point cloud into a Bird's-Eye View (BEV) range image and
broadcasts it as a PNG over WebSocket.

Algorithm
---------
1. Project every point onto the XY plane (top-down view).
2. Discretise the XY extent into a 2D grid of configurable resolution.
3. For each grid cell record:
   - ``height``   : maximum Z value of all points that fall in the cell.
   - ``density``  : number of points in the cell (point count).
   - ``intensity``: mean intensity of all points in the cell (if available).
4. Normalise each channel independently to [0, 255] uint8.
5. Encode as single-channel (height) or multi-channel PNG and publish
   the bytes on the node's WebSocket topic together with a JSON header.

The output PointCloud passed to downstream DAG nodes is the *original*
input — this node is side-effect-only regarding the image.  No points are
added, removed, or modified.

Parameters
----------
resolution : float
    Metres per pixel in the output image. Default 0.1 m (10 cm/pixel).
x_min, x_max : float
    Spatial extent in the X direction. Default ±25 m.
y_min, y_max : float
    Spatial extent in the Y direction. Default ±25 m.
channel : str
    Which channel to visualise: ``"height"`` | ``"density"`` | ``"intensity"``.
    Default ``"height"``.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import struct
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np
import open3d as o3d

try:
    from PIL import Image as _PIL_Image

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from ...base import PipelineOperation

logger = logging.getLogger(__name__)

_VALID_CHANNELS = {"height", "density", "intensity"}

# Column index in the 16-col schema
_COL_X = 0
_COL_Y = 1
_COL_Z = 2
_COL_INTENSITY = 13  # matches FIELD_MAP["intensity"]["idx"]


def _encode_png_bytes(arr: np.ndarray) -> bytes:
    """Encode a (H, W) uint8 numpy array as PNG bytes (grayscale).

    Falls back to a minimal hand-crafted PNG if Pillow is not installed.
    """
    if _HAS_PIL:
        img = _PIL_Image.fromarray(arr.astype(np.uint8), mode="L")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=False, compress_level=1)
        return buf.getvalue()

    # Minimal fallback: encode as raw PGM (netpbm) which is easy to parse
    # in JavaScript via a custom reader — kept for environments without Pillow.
    h, w = arr.shape
    header = f"P5\n{w} {h}\n255\n".encode("ascii")
    return header + arr.astype(np.uint8).tobytes()


def _normalise_channel(data: np.ndarray, filled_mask: np.ndarray) -> np.ndarray:
    """Map *data* (float) to uint8 [0, 255] over the filled cells only."""
    result = np.zeros(data.shape, dtype=np.uint8)
    if not filled_mask.any():
        return result
    vals = data[filled_mask]
    vmin, vmax = float(vals.min()), float(vals.max())
    if vmax > vmin:
        normed = (vals - vmin) / (vmax - vmin)
    else:
        normed = np.ones_like(vals)
    result[filled_mask] = (normed * 255.0).astype(np.uint8)
    return result


def _build_bev_frame(
    image_arr: np.ndarray,
    png_bytes: bytes,
    channel: str,
    resolution: float,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    width: int,
    height: int,
    n_pts: int,
    filled_cells: int,
) -> bytes:
    """Pack a BEV image into the binary WebSocket frame format.

    Frame layout: 4-byte magic ``b"BEVI"`` + 4-byte little-endian uint32 (JSON
    header length) + JSON header bytes + PNG payload bytes.
    """
    header_dict = {
        "type": "bev_image",
        "channel": channel,
        "resolution": resolution,
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "width": width,
        "height": height,
        "timestamp": time.time(),
        "point_count": n_pts,
        "filled_cells": filled_cells,
    }
    header_bytes = json.dumps(header_dict).encode("utf-8")
    return b"BEVI" + struct.pack("<I", len(header_bytes)) + header_bytes + png_bytes


class RangeImage(PipelineOperation):
    """
    Generates a Bird's-Eye View (BEV) range image from a point cloud.

    The PNG image is broadcast over WebSocket on the node's topic.
    The input point cloud is forwarded unchanged to downstream DAG nodes.
    """

    def __init__(
            self,
            resolution: float = 0.1,
            x_min: float = -25.0,
            x_max: float = 25.0,
            y_min: float = -25.0,
            y_max: float = 25.0,
            channel: str = "height",
    ) -> None:
        if float(resolution) <= 0:
            raise ValueError("resolution must be > 0")
        if float(x_min) >= float(x_max):
            raise ValueError("x_min must be < x_max")
        if float(y_min) >= float(y_max):
            raise ValueError("y_min must be < y_max")
        channel = str(channel).lower().strip()
        if channel not in _VALID_CHANNELS:
            raise ValueError(
                f"channel must be one of {sorted(_VALID_CHANNELS)}, got '{channel}'"
            )

        self.resolution = float(resolution)
        self.x_min = float(x_min)
        self.x_max = float(x_max)
        self.y_min = float(y_min)
        self.y_max = float(y_max)
        self.channel = channel

        # Compute grid dimensions
        self.width: int = max(1, int(np.ceil((self.x_max - self.x_min) / self.resolution)))
        self.height: int = max(1, int(np.ceil((self.y_max - self.y_min) / self.resolution)))

        # WebSocket topic — injected by the orchestrator config loader after
        # NodeFactory.create() returns (see managers/config.py). Declared here
        # as a typed stub so type checkers and read-before-write guards work.
        self._ws_topic: Optional[str] = None

    # ------------------------------------------------------------------
    # Core BEV computation (pure numpy, no Open3D dependency)
    # ------------------------------------------------------------------

    def _build_bev(self, points: np.ndarray) -> Tuple[np.ndarray, int]:
        """
        Build a (H, W) uint8 image from a (N, M≥3) float32 points array.

        Returns
        -------
        image : np.ndarray shape (H, W) dtype uint8
        filled_cells : int  — number of cells that contained at least one point
        """
        W, H = self.width, self.height

        # --- filter to ROI ---
        mask = (
                (points[:, _COL_X] >= self.x_min) & (points[:, _COL_X] < self.x_max) &
                (points[:, _COL_Y] >= self.y_min) & (points[:, _COL_Y] < self.y_max)
        )
        pts = points[mask]

        if pts.shape[0] == 0:
            return np.zeros((H, W), dtype=np.uint8), 0

        # --- discretise XY → pixel indices ---
        col_idx = np.clip(
            ((pts[:, _COL_X] - self.x_min) / self.resolution).astype(np.int32), 0, W - 1
        )
        # Image row 0 = y_max (north) so invert Y
        row_idx = np.clip(
            ((self.y_max - pts[:, _COL_Y]) / self.resolution).astype(np.int32), 0, H - 1
        )
        flat_idx = row_idx * W + col_idx

        # --- accumulate per-cell values ---
        filled = np.zeros(H * W, dtype=np.float32)
        np.add.at(filled, flat_idx, 1.0)  # reuse as count initially
        filled_mask_flat = filled > 0

        if self.channel == "density":
            channel_grid = filled.reshape(H, W)
            image = _normalise_channel(channel_grid, filled_mask_flat.reshape(H, W))

        elif self.channel == "height":
            z_grid = np.full(H * W, -np.inf, dtype=np.float32)
            np.maximum.at(z_grid, flat_idx, pts[:, _COL_Z])
            z_grid[~filled_mask_flat] = 0.0
            image = _normalise_channel(z_grid.reshape(H, W), filled_mask_flat.reshape(H, W))

        else:  # intensity
            n_cols = pts.shape[1]
            if n_cols > _COL_INTENSITY:
                sum_intensity = np.zeros(H * W, dtype=np.float32)
                count = np.zeros(H * W, dtype=np.float32)
                np.add.at(sum_intensity, flat_idx, pts[:, _COL_INTENSITY])
                np.add.at(count, flat_idx, 1.0)
                count_safe = np.where(count > 0, count, 1.0)
                mean_intensity = sum_intensity / count_safe
                mean_intensity[~filled_mask_flat] = 0.0
                image = _normalise_channel(mean_intensity.reshape(H, W), filled_mask_flat.reshape(H, W))
            else:
                # Fallback to density when intensity column is absent
                channel_grid = filled.reshape(H, W)
                image = _normalise_channel(channel_grid, filled_mask_flat.reshape(H, W))

        return image, int(filled_mask_flat.sum())

    # ------------------------------------------------------------------
    # PipelineOperation.apply()
    # ------------------------------------------------------------------

    def apply(self, pcd: Any) -> Tuple[Any, Dict[str, Any]]:
        """
        Generate BEV image, broadcast over WebSocket, return input pcd unchanged.
        """
        if not isinstance(pcd, o3d.t.geometry.PointCloud):
            raise TypeError(
                f"RangeImage expects o3d.t.geometry.PointCloud, "
                f"got {type(pcd).__name__}"
            )

        n_pts: int = (
            pcd.point.positions.shape[0] if "positions" in pcd.point else 0
        )
        metadata: Dict[str, Any] = {
            "channel": self.channel,
            "resolution_m": self.resolution,
            "image_width": self.width,
            "image_height": self.height,
            "point_count": n_pts,
        }

        if n_pts == 0:
            logger.debug("RangeImage: empty point cloud — skipping image generation")
            return pcd, metadata

        # Extract raw numpy for fast BEV accumulation
        positions: np.ndarray = pcd.point.positions.cpu().numpy()  # (N, 3)

        # Try to get intensity if present
        if "intensity" in pcd.point:
            intensity_col: np.ndarray = pcd.point["intensity"].cpu().numpy().flatten().reshape(-1, 1)
            # Pad to at least 14 columns so _COL_INTENSITY (13) is valid
            n_pad = max(0, _COL_INTENSITY + 1 - 3)
            pts_full = np.hstack([
                positions,
                np.zeros((positions.shape[0], n_pad - 1), dtype=np.float32),
                intensity_col,
            ])
        else:
            pts_full = positions

        # Build BEV image (pure numpy, runs in asyncio.to_thread via OperationNode)
        image_arr, filled_cells = self._build_bev(pts_full)

        metadata["filled_cells"] = filled_cells
        metadata["fill_ratio"] = round(
            filled_cells / max(1, self.width * self.height), 4
        )

        # Encode PNG
        try:
            png_bytes: bytes = _encode_png_bytes(image_arr)
        except Exception as exc:
            logger.warning("RangeImage: PNG encoding failed: %s", exc)
            return pcd, metadata

        # Broadcast the PNG image over WebSocket on this node's topic.
        # We fire-and-forget in the calling thread's event loop.
        frame = _build_bev_frame(
            image_arr=image_arr,
            png_bytes=png_bytes,
            channel=self.channel,
            resolution=self.resolution,
            x_min=self.x_min,
            x_max=self.x_max,
            y_min=self.y_min,
            y_max=self.y_max,
            width=self.width,
            height=self.height,
            n_pts=n_pts,
            filled_cells=filled_cells,
        )

        topic = self._ws_topic
        if topic:
            try:
                loop = asyncio.get_running_loop()
                from app.services.websocket.manager import manager as ws_manager
                asyncio.ensure_future(ws_manager.broadcast(topic, frame), loop=loop)
            except RuntimeError:
                # No running loop — unit-test / offline context, skip broadcast
                pass

        logger.debug(
            "RangeImage[%s]: %dx%d px, %d filled cells, PNG=%d bytes",
            self.channel,
            self.width,
            self.height,
            filled_cells,
            len(png_bytes),
        )

        # Return the original pcd unchanged so downstream nodes still receive points
        return pcd, metadata
