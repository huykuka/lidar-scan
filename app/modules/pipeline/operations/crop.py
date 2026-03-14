from typing import List

import numpy as np
import open3d as o3d

from ..base import PipelineOperation


class Crop(PipelineOperation):
    """
    Crops the point cloud using an axis-aligned bounding box.
    
    Args:
        min_bound (List[float]): Minimum coordinates [x, y, z].
        max_bound (List[float]): Maximum coordinates [x, y, z].
    """

    def __init__(self, min_bound, max_bound, invert=False):
        self.min_bound_np = np.asarray(min_bound, dtype=np.float64)
        self.max_bound_np = np.asarray(max_bound, dtype=np.float64)

        self.min_bound_t = o3d.core.Tensor(self.min_bound_np, dtype=o3d.core.Dtype.Float64)
        self.max_bound_t = o3d.core.Tensor(self.max_bound_np, dtype=o3d.core.Dtype.Float64)

        self.invert = invert

    def apply(self, pcd):

        # Tensor point cloud
        if isinstance(pcd, o3d.t.geometry.PointCloud):

            bbox = o3d.t.geometry.AxisAlignedBoundingBox(self.min_bound_t, self.max_bound_t)
            pcd = pcd.crop(bbox, invert=self.invert)

            count = int(pcd.point["positions"].shape[0]) if "positions" in pcd.point else 0

            return pcd, {"cropped_count": count}

        # Legacy point cloud
        elif isinstance(pcd, o3d.geometry.PointCloud):

            bbox = o3d.geometry.AxisAlignedBoundingBox(
                min_bound=self.min_bound_np,
                max_bound=self.max_bound_np
            )

            if self.invert:
                indices = bbox.get_point_indices_within_bounding_box(
                    np.asarray(pcd.points)
                )
                pcd = pcd.select_by_index(indices, invert=True)
            else:
                pcd = pcd.crop(bbox)

            return pcd, {"cropped_count": len(pcd.points)}

        else:
            raise TypeError("Unsupported point cloud type")
