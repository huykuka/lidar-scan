"""
filter/node.py — Generic and attribute-based point cloud filters.

Both operations are NUMPY_ONLY: apply() receives and returns a raw (N, M)
numpy array with no Open3D allocation or thread hop.

FilterByKey uses FIELD_MAP to translate named attributes (intensity, layer,
etc.) to column indices, then applies a standard comparison operator.
"""
from typing import Any, Callable, Tuple, Dict

import numpy as np

from ...base import PipelineOperation, FIELD_MAP


def _coerce_numeric(val: Any) -> Any:
    """Cast string numerics to float/int; leave all other types untouched."""
    if isinstance(val, str):
        try:
            return float(val) if '.' in val else int(val)
        except ValueError:
            pass
    return val


def _apply_operator(data: np.ndarray, op: str, val: Any) -> np.ndarray:
    """Apply a comparison operator and return a boolean mask."""
    val = _coerce_numeric(val)
    if op == '>':   return data > val
    if op == '>=':  return data >= val
    if op == '<':   return data < val
    if op == '<=':  return data <= val
    if op == '!=':  return data != val
    return data == val  # '==' and fallback


class Filter(PipelineOperation):
    """
    Generic point cloud filter using a custom callable.

    NUMPY_ONLY: ``filter_fn`` receives the (N, M) numpy array and must return
    a boolean mask (N,) or an integer index array.
    """

    NUMPY_ONLY = True

    def __init__(self, filter_fn: Callable[[np.ndarray], Any]) -> None:
        self.filter_fn = filter_fn

    def apply(self, pts: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        result = self.filter_fn(pts)
        if isinstance(result, np.ndarray) and result.dtype == bool:
            out = pts[result]
        else:
            out = pts[np.asarray(result)]
        return out, {"filtered_count": int(out.shape[0])}


class FilterByKey(PipelineOperation):
    """
    Filters the point cloud based on a named attribute column.

    NUMPY_ONLY: uses FIELD_MAP to look up the column index for ``key``,
    then applies a comparison without any Open3D overhead.

    ``value`` is either:
      - a scalar for equality matching
      - a ``(op, threshold)`` tuple  (op: '>' '>=' '<' '<=' '==' '!=')
      - a callable ``(col_array) -> bool_mask``
    """

    NUMPY_ONLY = True

    def __init__(self, key: str, value: Any) -> None:
        self.key = key
        if isinstance(value, str):
            try:
                value = float(value) if '.' in value else int(value)
            except ValueError:
                pass
        self.value = value

    def _get_column(self, pts: np.ndarray) -> np.ndarray:
        info = FIELD_MAP.get(self.key)
        if info is None:
            raise KeyError(f"FilterByKey: unknown key '{self.key}' — not in FIELD_MAP")
        idx = info["idx"]
        col = pts[:, idx]
        return col[:, 0] if col.ndim > 1 else col

    def _compute_mask(self, col: np.ndarray) -> np.ndarray:
        if callable(self.value):
            return np.asarray(self.value(col), dtype=bool)
        if isinstance(self.value, (tuple, list)) and len(self.value) == 2:
            op, val = self.value
            return _apply_operator(col, op, val)
        return col == _coerce_numeric(self.value)

    def apply(self, pts: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        try:
            col = self._get_column(pts)
        except KeyError as e:
            return pts, {"filtered_count": int(pts.shape[0]), "warning": str(e)}
        out = pts[self._compute_mask(col)]
        return out, {"filtered_count": int(out.shape[0]), "filter_key": self.key}
