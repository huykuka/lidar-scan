# lidar-standalone

A standalone Python backend for real-time LiDAR point cloud processing and streaming. Built with FastAPI, Open3D, and the SICK Scan API. Supports multiple sensors, modular processing pipelines, multi-sensor fusion, and live WebSocket streaming to a browser frontend.

![Demo](demo.png)

---

## Features

- **Multi-sensor support** — run multiple LiDAR sensors simultaneously, each in its own process
- **Modular pipeline system** — compose point cloud operations using a fluent builder API
- **Multi-sensor fusion** — merge point clouds from multiple sensors into a unified world-space cloud
- **Real-time WebSocket streaming** — binary point cloud data streamed to the frontend at full sensor rate
- **Simulation mode** — replay from a `.pcd` file without physical hardware
- **Sensor pose / transformation** — define each sensor's physical position and orientation; points are automatically transformed into world space

---

## Requirements

- Python 3.12+
- Docker (required to build the SICK Scan native library)

---

## Installation

### 1. Create Virtual Environment

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Build SICK Scan API

This script uses Docker to build the library and copy the artifacts (drivers, launch files, and Python API) into the project directory.

```bash
cd setup
./setup.sh
cd ..
```

---

## Running

### Real hardware

```bash
export LD_LIBRARY_PATH=.:./build:$LD_LIBRARY_PATH
export PYTHONPATH=.:./sick-scan-api/api:$PYTHONPATH
python3 main.py
```

### Simulation (PCD file replay)

```bash
./run_sim.sh
```

Frontend available at: `http://localhost:8004/static/index.html`

### Environment variables

| Variable         | Default                          | Description                  |
| ---------------- | -------------------------------- | ---------------------------- |
| `HOST`           | `0.0.0.0`                        | Server bind address          |
| `PORT`           | `8005`                           | Server port                  |
| `DEBUG`          | `false`                          | Enable hot-reload            |
| `LIDAR_MODE`     | `real`                           | `real` or `sim`              |
| `LIDAR_LAUNCH`   | `./launch/sick_multiscan.launch` | Launch file path             |
| `LIDAR_PCD_PATH` | `./test.pcd`                     | PCD file for simulation mode |

---

## Project Structure

```
app/
├── app.py                        # FastAPI app, sensor setup, startup
├── core/
│   └── config.py                 # Settings from environment variables
├── api/v1/
│   └── endpoints.py              # REST API routes
├── pipeline/
│   ├── base.py                   # PipelineOperation, PointCloudPipeline base classes
│   ├── factory.py                # PipelineFactory — resolves pipeline names to instances
│   ├── operations.py             # PipelineBuilder + all built-in operations
│   └── impl/
│       ├── basic.py              # Basic pipeline (downsample + outlier removal)
│       ├── advanced.py           # Advanced pipeline (stats, plane segmentation, debug export)
│       └── reflector.py          # Reflector detection pipeline (filter + cluster)
└── services/
    ├── lidar/
    │   ├── service.py            # LidarService — sensor management, transformation, broadcasting
    │   ├── lidar_worker.py       # Worker process for real hardware (SICK Scan API)
    │   ├── pcd_worker.py         # Worker process for PCD file simulation
    │   └── fusion.py             # FusionService — opt-in multi-sensor point cloud fusion
    └── websocket/
        └── manager.py            # WebSocket connection manager
```

---

## Sensor Setup

Sensors are registered in `app/app.py` using `lidar_service.generate_lidar()`:

```python
lidar_service.generate_lidar(
    sensor_id="lidar_front",
    launch_args="./launch/sick_multiscan.launch hostname:=192.168.1.10 udp_receiver_ip:=192.168.1.1",
    pipeline_name="advanced",   # optional — resolves via PipelineFactory
    mode="real",                # "real" or "sim"
    # Physical pose in world space (meters / radians):
    x=0.0, y=0.0, z=0.5,
    yaw=0.0, pitch=0.0, roll=0.0,
)
```

Each sensor runs in its own subprocess. Points are automatically transformed into world space using the sensor's pose before broadcasting.

---

## Pipeline System

Pipelines are composed using the fluent `PipelineBuilder` API and registered by name in `app/pipeline/factory.py`.

### Built-in operations

| Method                                         | Description                       |
| ---------------------------------------------- | --------------------------------- |
| `.crop(min, max)`                              | Axis-aligned bounding box crop    |
| `.downsample(voxel_size)`                      | Voxel grid downsampling           |
| `.uniform_downsample(every_k)`                 | Keep every k-th point             |
| `.remove_outliers(nb_neighbors, std_ratio)`    | Statistical outlier removal       |
| `.remove_radius_outliers(nb_points, radius)`   | Radius-based outlier removal      |
| `.segment_plane(distance_threshold)`           | RANSAC plane segmentation         |
| `.cluster(eps, min_points)`                    | DBSCAN clustering, removes noise  |
| `.filter(reflector=True, intensity=('>',0.5))` | Filter by point attribute         |
| `.debug_save(output_dir, prefix)`              | Save PCD snapshots to disk        |
| `.save_structure(output_file)`                 | Save point cloud metadata to JSON |
| `.add_custom(operation)`                       | Add a custom `PipelineOperation`  |

### Creating a new pipeline

1. Add a file in `app/pipeline/impl/my_pipeline.py`:

```python
from ..operations import PipelineBuilder

def create_pipeline(lidar_id: str = "default"):
    return (PipelineBuilder()
            .downsample(voxel_size=0.05)
            .remove_outliers(nb_neighbors=20, std_ratio=2.0)
            .build())
```

2. Register it in `app/pipeline/factory.py`:

```python
from .impl import basic, advanced, reflector, my_pipeline

_PIPELINE_MAP: dict[str, Callable] = {
    "basic":      basic.create_pipeline,
    "advanced":   advanced.create_pipeline,
    "reflector":  reflector.create_pipeline,
    "my_pipeline": my_pipeline.create_pipeline,   # ← add here
}

PipelineName = Literal["basic", "advanced", "reflector", "my_pipeline"]  # ← and here
```

3. Use it:

```python
lidar_service.generate_lidar(sensor_id="lidar1", ..., pipeline_name="my_pipeline")
```

---

## Multi-Sensor Fusion

`FusionService` is an opt-in module that merges point clouds from multiple sensors into a single unified cloud, broadcast on a dedicated WebSocket topic.

```python
from app.services.lidar.fusion import FusionService

# Option 1: Fuse ALL registered sensors
fusion = FusionService(lidar_service)
fusion.enable()

# Option 2: Fuse only specific sensors
fusion = FusionService(lidar_service, sensor_ids=["lidar_front", "lidar_rear"])
fusion.enable()

# Option 3: Multiple independent fusion groups on different topics
top_fusion    = FusionService(lidar_service, topic="top_fused",    sensor_ids=["lidar_top_left", "lidar_top_right"])
ground_fusion = FusionService(lidar_service, topic="ground_fused", sensor_ids=["lidar_front",    "lidar_rear"])
top_fusion.enable()
ground_fusion.enable()

# Option 4: Fuse + run a named pipeline on the merged cloud (same API as generate_lidar)
fusion = FusionService(
    lidar_service,
    topic="fused_reflectors",
    sensor_ids=["lidar_front", "lidar_rear"],
    pipeline_name="reflector",
)
fusion.enable()
```

Fusion only fires once **all expected sensors** have contributed at least one frame. Points are already in world space (transformation applied per-sensor) before merging.

---

## WebSocket Protocol

Data is broadcast as binary frames in the following format:

| Field       | Size         | Type         | Description          |
| ----------- | ------------ | ------------ | -------------------- |
| Magic       | 4 bytes      | `char[4]`    | `LIDR`               |
| Version     | 4 bytes      | `uint32`     | `1`                  |
| Timestamp   | 8 bytes      | `float64`    | Unix timestamp       |
| Point count | 4 bytes      | `uint32`     | Number of points `N` |
| Points      | N × 12 bytes | `float32[3]` | X, Y, Z per point    |

### Topics

| Topic                          | Description                                                   |
| ------------------------------ | ------------------------------------------------------------- |
| `{sensor_id}_processed_points` | Pipeline-processed points for a single sensor                 |
| `{sensor_id}_raw_points`       | Raw (unprocessed) points for a single sensor                  |
| `fused_points`                 | Merged cloud from all sensors (when FusionService is enabled) |
| _(custom)_                     | Any topic name passed to `FusionService(topic=...)`           |

---

## REST API

| Method | Path          | Description                                 |
| ------ | ------------- | ------------------------------------------- |
| `GET`  | `/`           | Serves the frontend (`index.html`)          |
| `GET`  | `/status`     | Returns running state and active sensor IDs |
| `GET`  | `/static/...` | Static frontend assets                      |
