from typing import List, Any, Callable
import time
import json
import os
import open3d as o3d
import numpy as np
from ..base import PipelineOperation, _tensor_map_keys

class Filter(PipelineOperation):
    """
    Generic point cloud filter that uses a custom filter function.
    
    Args:
        filter_fn (Callable): A function that takes a PointCloud and returns a boolean mask or indices.
                             - Tensor API: filter_fn(pcd) -> o3d.core.Tensor (bool or int64)
                             - Legacy API: filter_fn(pcd) -> np.ndarray (bool or int) or List[int]
    """

    def __init__(self, filter_fn: Callable[[Any], Any]):
        """
        filter_fn should take a PointCloud and return a boolean mask or indices.
        For Tensor API: filter_fn(pcd) -> o3d.core.Tensor (bool or int64)
        For Legacy API: filter_fn(pcd) -> np.ndarray (bool or int) or List[int]
        """
        self.filter_fn = filter_fn

    def apply(self, pcd: Any):
        result = self.filter_fn(pcd)

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            if hasattr(result, 'shape') and len(result.shape) > 1:
                result = result.reshape([-1])

            if hasattr(result, 'dtype') and str(result.dtype).lower().startswith('bool'):
                pcd = pcd.select_by_mask(result)
            else:
                pcd = pcd.select_by_index(result)
            if 'positions' in pcd.point:
                final_count = pcd.point.positions.shape[0]
            else:
                final_count = 0
        else:
            if isinstance(result, np.ndarray) and result.dtype == bool:
                result = np.where(result)[0]
            pcd = pcd.select_by_index(result)
            final_count = len(pcd.points)

        return pcd, {"filtered_count": final_count}

class FilterByKey(PipelineOperation):
    """
    Filters the point cloud based on a specific attribute key.
    
    Args:
        key (str): The attribute key to filter by (e.g., 'intensity', 'reflector').
        value (Any): The value to match, or a callable condition (e.g., lambda x: x > 0.5).
    """

    def __init__(self, key: str, value: Any):
        """
        Filters the point cloud based on a specific attribute (key).
        'value' can be a direct value (e.g., True, 0.5) for equality matching,
        or a condition function (e.g., lambda x: x > 0.5).
        """
        self.key = key
        
        if isinstance(value, str):
            try:
                value = float(value) if '.' in value else int(value)
            except ValueError:
                pass
        self.value = value

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            if self.key not in pcd.point:
                count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
                return pcd, {"filtered_count": count, "warning": f"Key '{self.key}' not found"}

            data = pcd.point[self.key]
            if callable(self.value):
                result = self.value(data)
            elif isinstance(self.value, (tuple, list)) and len(self.value) == 2:
                op, val = self.value
                
                # Cast string numerics to float, otherwise O3D tensor comparison throws TypeError
                if isinstance(val, str):
                    try:
                        val = float(val) if '.' in val else int(val)
                    except ValueError:
                        pass
                        
                if op == '>':
                    result = (data > val)
                elif op == '>=':
                    result = (data >= val)
                elif op == '<':
                    result = (data < val)
                elif op == '<=':
                    result = (data <= val)
                elif op == '!=':
                    result = (data != val)
                elif op == '==':
                    result = (data == val)
                else:
                    result = (data == val)
            else:
                result = (data == self.value)

            if hasattr(result, 'shape') and len(result.shape) > 1:
                result = result.reshape([-1])

            if hasattr(result, 'dtype') and str(result.dtype).lower().startswith('bool'):
                pcd = pcd.select_by_mask(result)
            else:
                pcd = pcd.select_by_index(result)
            
            if 'positions' in pcd.point:
                final_count = pcd.point.positions.shape[0]
            else:
                final_count = 0
        else:
            attr_name = self.key
            if self.key == "intensity": attr_name = "colors"

            if hasattr(pcd, attr_name):
                data = np.asarray(getattr(pcd, attr_name))
                if callable(self.value):
                    mask = self.value(data)
                elif isinstance(self.value, (tuple, list)) and len(self.value) == 2:
                    op, val = self.value
                    
                    if isinstance(val, str):
                        try:
                            val = float(val) if '.' in val else int(val)
                        except ValueError:
                            pass
                            
                    if op == '>':
                        mask = (data > val)
                    elif op == '>=':
                        mask = (data >= val)
                    elif op == '<':
                        mask = (data < val)
                    elif op == '<=':
                        mask = (data <= val)
                    elif op == '!=':
                        mask = (data != val)
                    elif op == '==':
                        mask = (data == val)
                    else:
                        mask = (data == val)
                else:
                    mask = (data == self.value)

                if isinstance(mask, np.ndarray) and mask.dtype == bool:
                    indices = np.where(mask)[0]
                else:
                    indices = mask

                pcd = pcd.select_by_index(indices)
                final_count = len(pcd.points)
            else:
                return pcd, {"filtered_count": len(pcd.points),
                             "warning": f"Attribute '{self.key}' not found on legacy PointCloud"}

        return pcd, {"filtered_count": final_count, "filter_key": self.key}

