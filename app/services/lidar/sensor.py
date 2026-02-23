import asyncio
import multiprocessing as mp
from typing import Any, Dict, List, Optional, cast

import numpy as np

from app.pipeline import PipelineFactory, PointCloudPipeline
from app.services.websocket.manager import manager
from .core import LidarSensor, transform_points, TopicRegistry
from .protocol import pack_points_binary


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
        self._topic_registry = TopicRegistry()
        # Runtime tracking for status endpoint
        self.lidar_runtime: Dict[str, Dict[str, Any]] = {}

    def load_config(self):
        """Loads sensor configurations from SQLite and registers them."""
        from app.repositories import FusionRepository, LidarRepository
        lidar_repo = LidarRepository()
        fusion_repo = FusionRepository()
        try:
            configs = lidar_repo.list()
            enabled_configs = [c for c in configs if bool(c.get("enabled", True))]
            for item in enabled_configs:
                sensor = self.generate_lidar(
                    sensor_id=item["id"],
                    name=item.get("name", item["id"]),
                    topic_prefix=item.get("topic_prefix"),
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
            print(f"Loaded {len(enabled_configs)} sensors from DB")
        except Exception as e:
            print(f"Error loading lidars from DB: {e}")

        # Load Fusions
        try:
            fusions_cfg = fusion_repo.list()
            from app.services.lidar.fusion import FusionService
            for item in fusions_cfg:
                if not bool(item.get("enabled", True)):
                    continue
                fusion = FusionService(
                    self,
                    topic=item.get("topic", "fused_points"),
                    sensor_ids=item.get("sensor_ids"),
                    pipeline_name=item.get("pipeline_name"),
                    fusion_id=item.get("id")
                )
                self.fusions.append(fusion)
        except Exception as e:
            print(f"Error loading fusions from DB: {e}")

    def reload_config(self, loop=None):
        """Stops all services, reloads config, and restarts."""
        was_running = self.is_running

        self.stop()
        self.sensors = []
        self._topic_registry.clear()
        for fusion in getattr(self, 'fusions', []):
            fusion.disable()
        self.fusions = []
        manager.reset_active_connections()
        self.load_config()

        # Ensure fusions interpret their sensor filter as sensor IDs (mapped to topic_prefix)
        for fusion in self.fusions:
            try:
                fusion.use_topic_prefix_filter(False)
            except Exception:
                pass
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
                       topic_prefix: Optional[str] = None,
                       pipeline_name: Optional[str] = None,
                       mode: str = "real", pcd_path: Optional[str] = None,
                       x: float = 0, y: float = 0, z: float = 0,
                       roll: float = 0, pitch: float = 0, yaw: float = 0):
        """
        Helper method to create and add a sensor with a specific pose in one call.
        If pipeline_name is provided and pipeline is None, it creates the pipeline automatically.
        """
        sensor_name = name or sensor_id
        desired_prefix = topic_prefix or sensor_name
        topic_prefix = self._topic_registry.register(desired_prefix, sensor_id)

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
        import time
        import os
        self._loop = loop or asyncio.get_event_loop()
        self.is_running = True
        
        # Recreate queue to ensure it's fresh after potential terminations
        # This prevents "corrupted queue" issues if a worker was terminated while writing
        self.data_queue = mp.Queue(maxsize=100)

        for sensor in self.sensors:
            stop_event = mp.Event()
            
            # Initialize runtime state for this sensor
            self.lidar_runtime[sensor.id] = {
                "last_frame_at": None,
                "last_error": None,
                "process_alive": False,
                "mode": sensor.mode,
            }

            try:
                if sensor.mode == "sim":
                    # Validate PCD path before spawning
                    if not sensor.pcd_path or not os.path.exists(sensor.pcd_path):
                        error_msg = f"PCD file not found: {sensor.pcd_path or '(not specified)'}"
                        print(f"[{sensor.id}] {error_msg}")
                        self.lidar_runtime[sensor.id]["last_error"] = error_msg
                        continue
                    
                    # Lazy import: open3d might not be installed in all environments
                    try:
                        from .workers.pcd import pcd_worker_process
                    except ImportError as e:
                        error_msg = f"open3d not available: {e}"
                        print(f"[{sensor.id}] {error_msg}")
                        self.lidar_runtime[sensor.id]["last_error"] = error_msg
                        continue
                    
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
                self.lidar_runtime[sensor.id]["process_alive"] = True
                print(f"Spawned worker for {sensor.id} (PID: {p.pid})")
            
            except Exception as e:
                error_msg = f"Failed to start worker: {e}"
                print(f"[{sensor.id}] {error_msg}")
                self.lidar_runtime[sensor.id]["last_error"] = error_msg

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
        import time
        try:
            lidar_id = payload["lidar_id"]
            timestamp = payload["timestamp"]
            
            # Update runtime tracking
            if lidar_id in self.lidar_runtime:
                self.lidar_runtime[lidar_id]["last_frame_at"] = time.time()
                self.lidar_runtime[lidar_id]["last_error"] = None

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
                points = transform_points(points, transformation)

                binary_data = pack_points_binary(points, timestamp)
                await manager.broadcast(f"{topic_prefix}_processed_points", binary_data)

                raw_points = payload.get("raw_points")
                if raw_points is not None:
                    raw_points = transform_points(raw_points, transformation)
                    binary_raw = pack_points_binary(raw_points, timestamp)
                    await manager.broadcast(f"{topic_prefix}_raw_points", binary_raw)
            else:
                # Unprocessed fallback
                points = payload.get("points")
                if points is not None:
                    points = transform_points(points, transformation)
                    binary_data = pack_points_binary(points, timestamp)
                    await manager.broadcast(f"{topic_prefix}_raw_points", binary_data)
        except Exception as e:
            print(f"Broadcasting error: {e}")
            # Track error in runtime state if we can identify the lidar
            lidar_id = payload.get("lidar_id")
            if lidar_id and lidar_id in self.lidar_runtime:
                self.lidar_runtime[lidar_id]["last_error"] = str(e)
