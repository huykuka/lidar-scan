import asyncio
import multiprocessing as mp
from typing import List, Dict, Any, Optional

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
                processed_data["lidar_id"] = lidar_id
                processed_data["timestamp"] = timestamp

                # Split for raw vs processed topics
                # We broadcast the original 'raw_points' if provided, else fallback to pipeline 'points'
                raw_points = payload.get("raw_points") or processed_data.get("points", [])
                
                raw_view = {
                    "points": raw_points,
                    "count": len(raw_points),
                    "timestamp": timestamp
                }
                await manager.broadcast(f"{lidar_id}_raw_points", raw_view)
                await manager.broadcast(f"{lidar_id}_processed_points", processed_data)
            else:
                # Fallback for unprocessed data
                await manager.broadcast(f"{lidar_id}_raw_points", payload)
        except Exception as e:
            print(f"Broadcasting error: {e}")
