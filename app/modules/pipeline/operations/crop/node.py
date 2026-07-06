import logging
from typing import Tuple, Dict, Any

import numpy as np

from ...base import PipelineOperation

logger = logging.getLogger(__name__)


class Crop(PipelineOperation):
    """
    Crops the point cloud using an axis-aligned bounding box.

    NUMPY_ONLY: apply() receives and returns a raw (N, M) numpy array.
    No Open3D allocation, no thread hop.

    Args:
        min_bound: Minimum coordinates [x, y, z].
        max_bound: Maximum coordinates [x, y, z].
        invert: Keep points *outside* the box instead of inside.
    """

    NUMPY_ONLY = True

    def __init__(self, min_bound, max_bound, invert=False):
        self.min_bound = np.asarray(min_bound, dtype=np.float64)
        self.max_bound = np.asarray(max_bound, dtype=np.float64)

        for i, axis in enumerate(['X', 'Y', 'Z']):
            if self.max_bound[i] < self.min_bound[i]:
                logger.warning(
                    "Crop bounding box: max_bound[%s]=%.2f < min_bound[%s]=%.2f. Auto-swapping.",
                    axis, self.max_bound[i], axis, self.min_bound[i],
                )
                self.min_bound[i], self.max_bound[i] = self.max_bound[i], self.min_bound[i]

        self.invert = bool(invert)

    def apply(self, pts: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        lo, hi = self.min_bound, self.max_bound
        mask = (
            (pts[:, 0] >= lo[0]) & (pts[:, 0] <= hi[0]) &
            (pts[:, 1] >= lo[1]) & (pts[:, 1] <= hi[1]) &
            (pts[:, 2] >= lo[2]) & (pts[:, 2] <= hi[2])
        )
        if self.invert:
            mask = ~mask
        out = pts[mask]
        return out, {"cropped_count": int(out.shape[0])}
