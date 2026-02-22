import asyncio
import multiprocessing as mp
import re
import struct
from typing import Any, Dict, List, Optional, cast

import numpy as np

from app.pipeline import PipelineFactory, PointCloudPipeline
from app.services.websocket.manager import manager


class LidarSensor:
    """Represents a single Lidar sensor and its processing pipeline configuration"""

    name: str
    topic_prefix: str

    def __init__(self, sensor_id: str, launch_args: str, pipeline: Optional[PointCloudPipeline] = None,
                  pipeline_name: Optional[str] = None,
                  mode: str = "real",
                 pcd_path: Optional[str] = None,
                 transformation: Optional[np.ndarray] = None,
                 name: Optional[str] = None,
                 topic_prefix: Optional[str] = None):
        self.id = sensor_id
        self.name = name or sensor_id
        self.topic_prefix = topic_prefix or self.name
        self.launch_args = launch_args
        self.pipeline = pipeline
        self.pipeline_name = pipeline_name
        self.mode = mode
        self.pcd_path = pcd_path
        # 4x4 Transformation matrix (Identity by default)
        self.transformation = transformation if transformation is not None else np.eye(4)
        self.pose_params = {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0}

    def set_pose(self, x: float, y: float, z: float, roll: float = 0, pitch: float = 0, yaw: float = 0):
        """
        Sets the transformation matrix using translation (meters) and rotation (degrees).
        """
        # Convert degrees to radians for internal math
        roll_rad = np.radians(roll)
        pitch_rad = np.radians(pitch)
        yaw_rad = np.radians(yaw)

        # Translation
        T = np.eye(4)
        T[:3, 3] = [x, y, z]

        # Rotation (Z-Y-X order)
        cr, sr = np.cos(roll_rad), np.sin(roll_rad)
        cp, sp = np.cos(pitch_rad), np.sin(pitch_rad)
        cy, sy = np.cos(yaw_rad), np.sin(yaw_rad)

        R = np.array([
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr]
        ])

        T[:3, :3] = R
        self.pose_params = {"x": x, "y": y, "z": z, "roll": roll, "pitch": pitch, "yaw": yaw}
        self.transformation = T
        return self


class LidarService:
    def __init__(self):
        self.sensors: List[LidarSensor] = []
        self.fusions: List[Any] = []
        self.processes: Dict[str, mp.Process] = {}
        self.stop_events: Dict[str, Any] = {}
        self.data_queue: Any = mp.Queue(maxsize=100)
        self.is_running = False
        self._loop: Any = None
        self._listener_task: Any = None
        self._topic_prefixes_in_use: set[str] = set()

    def _slugify_topic_prefix(self, name: str) -> str:
        # Keep websocket topics URL-friendly and stable.
        # - Replace non [A-Za-z0-9_-] with underscore
        # - Collapse repeats, strip edges
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip())
        base = re.sub(r"_+", "_", base).strip("_-")
        return base or "sensor"

    def _unique_topic_prefix(self, desired: str, sensor_id: str) -> str:
        base = self._slugify_topic_prefix(desired)
        if base not in self._topic_prefixes_in_use:
            self._topic_prefixes_in_use.add(base)
            return base

        suffix = self._slugify_topic_prefix(sensor_id)[:8]
        candidate = f"{base}_{suffix}" if suffix else f"{base}_1"
        i = 2
        while candidate in self._topic_prefixes_in_use:
            candidate = f"{base}_{suffix}_{i}" if suffix else f"{base}_{i}"
            i += 1
        self._topic_prefixes_in_use.add(candidate)
        return candidate

    def load_config(self):
        """Loads sensor configurations from SQLite and registers them."""
        from app.db import get_lidars, get_fusions
        try:
            configs = get_lidars()
            for item in configs:
                sensor = self.generate_lidar(
                    sensor_id=item["id"],
                    name=item.get("name", item["id"]),
                    launch_args=item["launch_args"],
                    pipeline_name=item.get("pipeline_name"),
                    mode=item.get("mode", "real"),
                    pcd_path=item.get("pcd_path"),
                    x=item.get("x", 0),
                    y=item.get("y", 0),
                    z=item.get("z", 0),
                    roll=item.get("roll", 0),
                    pitch=item.get("pitch", 0),
                    yaw=item.get("yaw", 0)
                )
            print(f"Loaded {len(configs)} sensors from DB")
        except Exception as e:
            print(f"Error loading lidars from DB: {e}")

        # Load Fusions
        try:
            fusions_cfg = get_fusions()
            from app.services.lidar.fusion import FusionService
            for item in fusions_cfg:
                fusion = FusionService(
                    self,
                    topic=item.get("topic", "fused_points"),
                    sensor_ids=item.get("sensor_ids"),
                    pipeline_name=item.get("pipeline_name")
                )
                self.fusions.append(fusion)
        except Exception as e:
            print(f"Error loading fusions from DB: {e}")

    def reload_config(self, loop=None):
        """Stops all services, reloads config, and restarts."""
        was_running = self.is_running

        self.stop()
        self.sensors = []
        self._topic_prefixes_in_use.clear()
        for fusion in getattr(self, 'fusions', []):
            fusion.disable()
        self.fusions = []
        manager.reset_active_connections()
        self.load_config()
        if was_running:
            self.start(loop or self._loop)

    def get_pipelines(self) -> List[str]:
        """Returns available pipeline names from the factory."""
        from app.pipeline.factory import _PIPELINE_MAP
        return list(_PIPELINE_MAP.keys())

    def add_sensor(self, sensor: LidarSensor):
        self.sensors.append(sensor)
        return self

    def generate_lidar(self, sensor_id: str, launch_args: str,
                       name: Optional[str] = None,
                       pipeline_name: Optional[str] = None,
                       mode: str = "real", pcd_path: Optional[str] = None,
                       x: float = 0, y: float = 0, z: float = 0,
                       roll: float = 0, pitch: float = 0, yaw: float = 0):
        """
        Helper method to create and add a sensor with a specific pose in one call.
        If pipeline_name is provided and pipeline is None, it creates the pipeline automatically.
        """
        sensor_name = name or sensor_id
        topic_prefix = self._unique_topic_prefix(sensor_name, sensor_id=sensor_id)

        pipeline = None
        if pipeline_name is not None:
            # PipelineName is derived from the factory registry at import time.
            # Some type checkers can't narrow/cast it cleanly, so we cast via Any.
            pipeline = PipelineFactory.get(cast(Any, pipeline_name), lidar_id=sensor_id)
            if pipeline:
                manager.register_topic(f"{topic_prefix}_processed_points")
                
        sensor = LidarSensor(
            sensor_id=sensor_id,
            name=sensor_name,
            topic_prefix=topic_prefix,
            launch_args=launch_args,
            pipeline=pipeline,
            pipeline_name=pipeline_name,
            mode=mode,
            pcd_path=pcd_path
        )
        sensor.set_pose(x, y, z, roll, pitch, yaw)
        self.add_sensor(sensor)

        # Register topics in the connection manager
        manager.register_topic(f"{topic_prefix}_raw_points")

        return sensor

    def start(self, loop=None):
        self._loop = loop or asyncio.get_event_loop()
        self.is_running = True
        
        # Recreate queue to ensure it's fresh after potential terminations
        # This prevents "corrupted queue" issues if a worker was terminated while writing
        self.data_queue = mp.Queue(maxsize=100)

        for sensor in self.sensors:
            stop_event = mp.Event()

            if sensor.mode == "sim":
                # Lazy import: open3d might not be installed in all environments
                from .workers.pcd import pcd_worker_process
                p = mp.Process(
                    target=pcd_worker_process,
                    args=(sensor.id, sensor.pcd_path or "", sensor.pipeline, self.data_queue, stop_event),
                    name=f"PcdWorker-{sensor.id}",
                    daemon=True
                )
            else:
                # Lazy import: sick_scan_api might not be installed in all environments
                from .workers.sick_scan import lidar_worker_process
                p = mp.Process(
                    target=lidar_worker_process,
                    args=(sensor.id, sensor.launch_args, sensor.pipeline, self.data_queue, stop_event),
                    name=f"LidarWorker-{sensor.id}",
                    daemon=True
                )

            p.start()

            self.processes[sensor.id] = p
            self.stop_events[sensor.id] = stop_event
            print(f"Spawned worker for {sensor.id} (PID: {p.pid})")

        for fusion in self.fusions:
            fusion.enable()

        self._listener_task = asyncio.create_task(self._queue_listener())

    def stop(self):
        self.is_running = False
        if self._listener_task:
            self._listener_task.cancel()

        for stop_event in self.stop_events.values():
            stop_event.set()

        for p in self.processes.values():
            p.join(timeout=1.0)
            if p.is_alive():
                p.terminate()

        print("All Lidar services stopped.")

    async def _queue_listener(self):
        loop = asyncio.get_event_loop()
        while self.is_running:
            try:
                if not self.data_queue.empty():
                    payload = await loop.run_in_executor(None, self.data_queue.get)
                    await self._handle_incoming_data(payload)
                else:
                    await asyncio.sleep(0.005)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Listener error: {e}")
                await asyncio.sleep(0.1)

    async def _handle_incoming_data(self, payload: Dict[str, Any]):
        try:
            lidar_id = payload["lidar_id"]
            timestamp = payload["timestamp"]

            # Find the sensor to get its transformation matrix
            sensor = next((s for s in self.sensors if s.id == lidar_id), None)
            transformation = sensor.transformation if sensor else np.eye(4)
            topic_prefix = sensor.topic_prefix if sensor else lidar_id

            if payload.get("processed"):
                # Data already processed by the worker's pipeline
                processed_data = payload["data"]

                # Extract points (they should be numpy arrays now)
                points = processed_data.get("points")
                if points is None:
                    # In case of some legacy or error
                    return

                # Apply transformation to bring points into world/global space
                points = self._transform_points(points, transformation)

                binary_data = self._pack_binary(points, timestamp)
                await manager.broadcast(f"{topic_prefix}_processed_points", binary_data)

                raw_points = payload.get("raw_points")
                if raw_points is not None:
                    raw_points = self._transform_points(raw_points, transformation)
                    binary_raw = self._pack_binary(raw_points, timestamp)
                    await manager.broadcast(f"{topic_prefix}_raw_points", binary_raw)
            else:
                # Unprocessed fallback
                points = payload.get("points")
                if points is not None:
                    points = self._transform_points(points, transformation)
                    binary_data = self._pack_binary(points, timestamp)
                    await manager.broadcast(f"{topic_prefix}_raw_points", binary_data)
        except Exception as e:
            print(f"Broadcasting error: {e}")

    def _pack_binary(self, points: np.ndarray, timestamp: float) -> bytes:
        """
        Packs points into binary format:
        Magic (4 bytes): 'LIDR'
        Version (4 bytes): 1 (uint32)
        Timestamp (8 bytes): float64
        Point Count (4 bytes): uint32
        Points (N * 12 bytes): x, y, z as float32
        """
        magic = b'LIDR'
        version = 1
        count = len(points)

        header = struct.pack('<4sIdI', magic, version, timestamp, count)

        # Ensure we only send X, Y, Z (first 3 columns) to match the (N * 12 bytes) format
        points_xyz = points[:, :3].astype(np.float32)
        return header + points_xyz.tobytes()

    def _transform_points(self, points: np.ndarray, T: np.ndarray) -> np.ndarray:
        """
        Applies a 4x4 transformation matrix T to (N, 3) or (N, M) points.
        Efficiently handles rotation and translation using numpy.
        """
        if points is None or len(points) == 0:
            return points

        # Skip if identity matrix
        if np.array_equal(T, np.eye(4)):
            return points

        # R is top-left 3x3, t is top-right 3x1
        R = T[:3, :3]
        t = T[:3, 3]

        # Apply transformation only to the first 3 columns (x, y, z)
        # points_transformed = points * R^T + t
        transformed = points.copy()
        transformed[:, :3] = points[:, :3] @ R.T + t
        return transformed
