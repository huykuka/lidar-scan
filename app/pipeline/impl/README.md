# Pipeline Implementation Guide

This directory contains concrete implementations of point cloud processing pipelines.

## How to Declare a New Pipeline

To add a new processing configuration, follow these steps:

### 1. Create the Implementation File

Create a new Python file in this directory (e.g., `my_special_lidar.py`). Every pipeline file must implement a `create_pipeline()` function that returns a `PointCloudPipeline` object.

```python
from ..operations import PipelineBuilder

def create_pipeline():
    return (PipelineBuilder()
            .crop(min_bound=[-5, -5, -1], max_bound=[5, 5, 5])
            .downsample(voxel_size=0.05)
            .cluster(eps=0.3, min_points=15)
            .build())
```

### 2. Register the Pipeline

Open `app/pipeline/factory.py` and add your new module to the `_PIPELINE_MAP`:

```python
from .impl import basic, advanced, my_special_lidar

_PIPELINE_MAP = {
    "basic": basic.create_pipeline,
    "advanced": advanced.create_pipeline,
    "special": my_special_lidar.create_pipeline,  # Add this
}
```

### 3. Use in the Main Application

In `app/app.py`, you can now request this pipeline by its name:

```python
pipeline = PipelineFactory.get("special")
```

## Adding Custom Operations

If you need logic not covered by the standard operations (`Crop`, `Downsample`, etc.), you can define a custom operation within your implementation file:

```python
from ..base import PipelineOperation

class MyCustomFilter(PipelineOperation):
    def apply(self, pcd):
        # ... perform Open3D logic ...
        return {"custom_metric": 42}

def create_pipeline():
    return (PipelineBuilder()
            .add_custom(MyCustomFilter())
            .build())
```

## Standard Operations Available

The `PipelineBuilder` currently supports:

- `.crop(min_bound, max_bound)`
- `.downsample(voxel_size)`
- `.remove_outliers(nb_neighbors, std_ratio)`
- `.segment_plane(distance_threshold)`
- `.cluster(eps, min_points)`
- `.add_custom(operation_object)`
