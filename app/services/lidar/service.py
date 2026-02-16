import asyncio
import struct
import multiprocessing as mp
from typing import List, Dict, Any, Optional

import numpy as np

from app.services.websocket.manager import manager
from .lidar_worker import lidar_worker_process
from .pcd_worker import pcd_worker_process


class LidarSensor:
    """Represents a single Lidar sensor and its processing pipeline configuration"""

    def __init__(self, sensor_id: str, launch_args: str, pipeline: Optional[Any] = None, mode: str = "real",
                 pcd_path: str = None):
        self.id = sensor_id
        self.launch_args = launch_args
        self.pipeline = pipeline
        self.mode = mode
        self.pcd_path = pcd_path


class LidarService:
    def __init__(self):
        self.sensors: List[LidarSensor] = []
        self.processes: Dict[str, mp.Process] = {}
        self.stop_events: Dict[str, mp.Event] = {}
        self.data_queue = mp.Queue(maxsize=100)
        self.is_running = False
        self._loop = None
        self._listener_task = None

    def add_sensor(self, sensor: LidarSensor):
        self.sensors.append(sensor)
        return self

    def start(self, loop=None):
        self._loop = loop or asyncio.get_event_loop()
        self.is_running = True

        for sensor in self.sensors:
            stop_event = mp.Event()

            if sensor.mode == "sim":
                p = mp.Process(
                    target=pcd_worker_process,
                    args=(sensor.id, sensor.pcd_path, sensor.pipeline, self.data_queue, stop_event),
                    name=f"PcdWorker-{sensor.id}",
                    daemon=True
                )
            else:
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

            if payload.get("processed"):
                # Data already processed by the worker's pipeline
                processed_data = payload["data"]
                
                # Extract points (they should be numpy arrays now)
                points = processed_data.get("points")
                if points is None:
                    # In case of some legacy or error
                    return

                # Pack processed points binary
                binary_data = self._pack_binary(points, timestamp)
                await manager.broadcast(f"{lidar_id}_processed_points", binary_data)

                # Broadcoast raw points if requested/available
                raw_points = payload.get("raw_points")
                if raw_points is not None:
                    binary_raw = self._pack_binary(raw_points, timestamp)
                    await manager.broadcast(f"{lidar_id}_raw_points", binary_raw)
            else:
                # Unprocessed fallback
                points = payload.get("points")
                if points is not None:
                    binary_data = self._pack_binary(points, timestamp)
                    await manager.broadcast(f"{lidar_id}_raw_points", binary_data)
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
        
        # Ensure points are float32 and reshaped correctly for binary append
        points_f32 = points.astype(np.float32)
        return header + points_f32.tobytes()
