# Shape Fitting Operation

Fits geometric primitives to input point clouds via RANSAC, then outputs a
downsampled point cloud sampled uniformly on the fitted shape surface.

## Structure

```
shape_fitting/
├── __init__.py   # Re-exports ShapeFitting
├── base.py       # ShapeFitterBase ABC + shared utilities
├── circle.py     # CircleFitter (ring or filled disc)
├── plane.py      # PlaneFitter (grid on fitted plane)
├── node.py       # ShapeFitting PipelineOperation (dispatcher)
└── README.md     # This file
```

## Adding a New Shape

1. Create `<shape>.py` in this directory (e.g. `cylinder.py`)
2. Subclass `ShapeFitterBase` from `base.py`
3. Implement the `fit(positions: np.ndarray)` method:
   - Input: `(N, 3)` float64 XYZ positions
   - Return: `(sampled_xyz, params_dict, shapes_list)` or `None` on failure
     - `sampled_xyz`: `(M, 3)` numpy array of points sampled on the shape
     - `params_dict`: dict of fitted parameters (serializable)
     - `shapes_list`: list of visual Shape objects for frontend (or empty)
4. Register in `node.py` `_FITTER_MAP`:
   ```python
   from .cylinder import CylinderFitter
   _FITTER_MAP = {
       ...
       "cylinder": CylinderFitter,
   }
   ```

## Template for a New Fitter

```python
"""<Shape> fitter."""
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from .base import ShapeFitterBase


class <Shape>Fitter(ShapeFitterBase):

    def fit(self, positions: np.ndarray) -> Optional[Tuple[np.ndarray, Dict[str, Any], List[Any]]]:
        # 1. RANSAC fit (use pyransac3d or custom)
        # 2. Optional: self.refine → scipy least_squares
        # 3. Sample self.num_output_points on the shape
        #    - Use self.fill to decide edge-only vs solid surface
        # 4. Return (sampled_xyz, params, shapes)
        ...
```

## Available Base Utilities (`ShapeFitterBase`)

| Method | Purpose |
|--------|---------|
| `self.estimate_normal(points)` | PCA-based normal estimation |
| `self.build_orthonormal_basis(normal)` | Returns `(u, v)` vectors in the plane |

## Config Parameters (all shapes)

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `shape` | str | `"circle"` | Shape type key |
| `thresh` | float | `0.01` | RANSAC inlier threshold (m) |
| `max_iterations` | int | `1000` | RANSAC iterations |
| `num_output_points` | int | `128` | Points to sample on fitted shape |
| `fill` | bool | `false` | Solid surface vs edge only |
| `refine` | bool | `true` | Scipy least_squares refinement |
| `emit_shapes` | bool | `true` | Emit visual shapes in metadata |

## Dependencies

- `pyransac3d` — RANSAC primitive fitting
- `scipy` (optional) — least_squares refinement
- `numpy` — everything else
