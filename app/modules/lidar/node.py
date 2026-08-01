"""
LiDAR sensor model representing configuration and state.
"""
import asyncio
import multiprocessing as mp
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

import numpy as np

from app.core.logging import get_logger
from app.modules.lidar.core import (
    create_transformation_matrix,
    gravity_to_roll_pitch,
    imu_gravity_alignment_matrix,
    imu_orientation_matrix,
    quaternion_is_valid,
    quaternion_to_rpy,
)
from app.schemas.pose import Pose
from app.schemas.status import NodeStatusUpdate, OperationalState, ApplicationState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)


@dataclass
class ImuSnapshot:
    """Latest IMU reading from the sensor's built-in inertial measurement unit."""

    timestamp: float = 0.0
    orientation: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0})
    angular_velocity: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    linear_acceleration: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "orientation": dict(self.orientation),
            "angular_velocity": dict(self.angular_velocity),
            "linear_acceleration": dict(self.linear_acceleration),
        }


class LidarSensor(ModuleNode):
    """Represents a single Lidar sensor and its processing pipeline configuration"""

    name: str
    topic_prefix: str

    def __init__(
            self,
            manager: Any,
            sensor_id: str,
            launch_args: str,
            transformation: Optional[np.ndarray] = None,
            name: Optional[str] = None,
            topic_prefix: Optional[str] = None,
            throttle_ms: float = 0,
            imu_auto_level: bool = False,
    ):
        self.manager = manager
        self.id = sensor_id
        self.name = name or sensor_id
        self.topic_prefix = topic_prefix or self.name
        self.launch_args = launch_args

        # LiDAR model information (set externally by build_sensor after instantiation)
        self.lidar_type: str = "multiscan136"
        self.lidar_display_name: str = "SICK multiScan136"

        self.transformation = transformation if transformation is not None else np.eye(4)
        self.pose_params: Pose = Pose.zero()

        # IMU state
        self.latest_imu: Optional[ImuSnapshot] = None
        self.imu_auto_level: bool = imu_auto_level
        self._imu_gravity_matrix: Optional[np.ndarray] = None

        # Latest world-frame frame, cached for one-shot floor calibration
        self._latest_points: Optional[np.ndarray] = None

        self._process = None
        self._stop_event = None
        self._cycle_time_ms: Optional[float] = None  # last frame processing duration

    def set_pose(self, pose: Pose) -> "LidarSensor":
        """Set the sensor pose and recompute the transformation matrix.

        Args:
            pose: Canonical 6-DOF Pose instance.

        Returns:
            self — to allow method chaining.
        """
        self.transformation = create_transformation_matrix(**pose.to_flat_dict())
        self.pose_params = pose
        return self

    def get_pose_params(self) -> Pose:
        """Return the current sensor pose as a Pose instance."""
        return self.pose_params

    async def on_input(self, payload: Dict[str, Any]):
        """Standard ModuleNode interface - delegates to handle_data"""
        # LidarSensor is a source node, so it doesn't receive input from upstream.
        # This method exists to satisfy the ModuleNode interface.
        pass

    def start(self, data_queue: Optional[mp.Queue] = None, runtime_status: Optional[Dict[str, Any]] = None):
        """Starts the worker process for this sensor"""
        if data_queue is None or runtime_status is None:
            raise ValueError("LidarSensor requires data_queue and runtime_status")

        # Check if process is already running
        if self._process and self._process.is_alive():
            logger.warning(f"[{self.id}] Worker process already running (PID: {self._process.pid}), skipping start")
            return

        self._stop_event = mp.Event()

        runtime_status[self.id] = {
            "last_frame_at": None,
            "last_error": None,
            "process_alive": False,
            "connection_status": "starting",
        }

        try:
            from app.modules.lidar.workers.real import lidar_worker_process
            self._process = mp.Process(
                target=lidar_worker_process,
                args=(self.id, self.launch_args, data_queue, self._stop_event),
                name=f"LidarWorker-{self.id}",
                daemon=True
            )

            self._process.start()
            runtime_status[self.id]["process_alive"] = True
            logger.info(f"Spawned worker for {self.id} (PID: {self._process.pid})")

            # Notify status change after starting
            notify_status_change(self.id)
        except Exception as e:
            error_msg = f"Failed to start worker: {e}"
            logger.error(f"[{self.id}] {error_msg}", exc_info=True)
            runtime_status[self.id]["last_error"] = error_msg
            notify_status_change(self.id)

    def stop(self):
        """Stops the worker process for this sensor"""
        if self._stop_event:
            self._stop_event.set()

        if self._process and self._process.is_alive():
            logger.info(f"[{self.id}] Stopping worker process (PID: {self._process.pid})...")

            # Worker calls os._exit(0) immediately on intentional stop,
            # so this join typically returns in well under 1s.
            self._process.join(timeout=1.0)

            if self._process.is_alive():
                logger.warning(f"[{self.id}] Worker didn't stop after 1s, killing...")
                self._process.kill()
                self._process.join(timeout=1.0)

        self._process = None
        self._stop_event = None
        logger.info(f"[{self.id}] Worker process stopped.")

        # Notify status change after stopping
        notify_status_change(self.id)

    async def handle_data(self, payload: Dict[str, Any], runtime_status: Dict[str, Any]):
        """Handles incoming data explicitly for this Lidar node"""
        from .core.transformations import transform_points

        try:
            timestamp = payload["timestamp"]
            event_type = payload.get("event_type")

            if event_type:
                if self.id in runtime_status:
                    if event_type == "connected":
                        runtime_status[self.id]["last_error"] = None
                        runtime_status[self.id]["connection_status"] = "connected"
                        logger.info(f"[{self.id}] Connected: {payload.get('message', '')}")
                        notify_status_change(self.id)
                    elif event_type == "disconnected":
                        runtime_status[self.id][
                            "last_error"] = f"Disconnected: {payload.get('message', 'Connection lost')}"
                        runtime_status[self.id]["connection_status"] = "disconnected"
                        logger.warning(f"[{self.id}] Disconnected: {payload.get('message', '')}")
                        notify_status_change(self.id)
                    elif event_type == "error":
                        runtime_status[self.id]["last_error"] = payload.get("message", "Unknown error")
                        runtime_status[self.id]["connection_status"] = "error"
                        logger.error(f"[{self.id}] Error: {payload.get('message', '')}")
                        notify_status_change(self.id)
                return

            if self.id in runtime_status:
                runtime_status[self.id]["last_frame_at"] = time.time()
                runtime_status[self.id]["last_error"] = None
                runtime_status[self.id]["connection_status"] = "connected"
                # Increment frame counter for debug logging
                frame_count = runtime_status[self.id].get("frame_count", 0) + 1
                runtime_status[self.id]["frame_count"] = frame_count

            # Extract and store IMU data if present
            imu_raw = payload.get("imu")
            if imu_raw is not None:
                orientation = imu_raw.get("orientation", {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0})
                acc = imu_raw.get("linear_acceleration", {"x": 0.0, "y": 0.0, "z": 0.0})
                self.latest_imu = ImuSnapshot(
                    timestamp=imu_raw.get("timestamp", 0.0),
                    orientation=orientation,
                    angular_velocity=imu_raw.get("angular_velocity", {"x": 0.0, "y": 0.0, "z": 0.0}),
                    linear_acceleration=acc,
                )
                if self.imu_auto_level:
                    # Primary: use orientation quaternion (matches SICK SDK convention)
                    qw, qx, qy, qz = orientation["w"], orientation["x"], orientation["y"], orientation["z"]
                    if quaternion_is_valid(qw, qx, qy, qz):
                        self._imu_gravity_matrix = imu_orientation_matrix(qw, qx, qy, qz)
                    else:
                        # Fallback: derive leveling from raw accelerometer gravity
                        self._imu_gravity_matrix = imu_gravity_alignment_matrix(
                            acc["x"], acc["y"], acc["z"],
                        )

            points = payload.get("points")
            if points is not None:
                # 1. Build effective transformation:
                #    pose_transform @ imu_gravity_correction (when auto-level is on)
                effective_T = self.transformation
                if self.imu_auto_level and self._imu_gravity_matrix is not None:
                    effective_T = self.transformation @ self._imu_gravity_matrix

                # 2. Transform points to world space off the main thread
                _frame_start = time.monotonic()
                transformed_points = transform_points(points, effective_T)
                # Update payload for downstream
                payload["points"] = transformed_points
                # Cache latest world-frame cloud for one-shot floor calibration
                self._latest_points = transformed_points

                frame_count = runtime_status.get(self.id, {}).get("frame_count", 0)
                if frame_count % 100 == 1:
                    logger.debug(f"[{self.id}] Frame #{frame_count}: {len(transformed_points)} points after transform")

                # 2. Forward to downstream nodes via Manager (fire-and-forget)
                asyncio.create_task(self.manager.forward_data(self.id, payload))
                self._cycle_time_ms = (time.monotonic() - _frame_start) * 1000

        except Exception as e:
            logger.error(f"Error handling data for {self.id}: {e}", exc_info=True)
            if self.id in runtime_status:
                runtime_status[self.id]["last_error"] = str(e)

    def calibrate_from_imu(self) -> Optional[Pose]:
        """Snapshot current IMU orientation and bake it into the sensor pose.

        Uses the orientation quaternion from the sick_scan_xd IMU callback
        (sensor→world rotation) to derive roll/pitch.  Falls back to the
        gravity vector when the quaternion is not available.

        The derived angles are stored directly into the pose — this is
        equivalent to how SICK's own SDK applies the quaternion RPY to the
        point cloud transform.

        Returns:
            The new Pose if successful, None if no IMU data is available.
        """
        if self.latest_imu is None:
            return None

        # Primary: orientation quaternion (per sick_scan_xd convention)
        quat = self.latest_imu.orientation
        qw, qx, qy, qz = quat["w"], quat["x"], quat["y"], quat["z"]

        if quaternion_is_valid(qw, qx, qy, qz):
            roll, pitch, _yaw = quaternion_to_rpy(qw, qx, qy, qz)
        else:
            # Fallback: gravity vector (negate to match sensor→world direction)
            acc = self.latest_imu.linear_acceleration
            g_roll, g_pitch = gravity_to_roll_pitch(acc["x"], acc["y"], acc["z"])
            roll, pitch = -g_roll, -g_pitch

        # Clamp to valid Pose range [-180, +180]
        roll = max(-180.0, min(180.0, roll))
        pitch = max(-180.0, min(180.0, pitch))

        current = self.pose_params
        new_pose = Pose(
            x=current.x,
            y=current.y,
            z=current.z,
            roll=roll,
            pitch=pitch,
            yaw=current.yaw,
        )

        self.set_pose(new_pose)

        # Persist to database
        from app.repositories.node_orm import NodeRepository
        NodeRepository().update_node_pose(self.id, new_pose)

        logger.info(
            f"[{self.id}] IMU calibration applied: roll={roll:.2f}° pitch={pitch:.2f}°"
        )
        return new_pose

    def calibrate_from_floor(
            self,
            distance_threshold: float = 0.05,
            max_planes: int = 3,
            min_inliers: int = 50,
            verticality_threshold: float = 0.7,
    ) -> Pose:
        """Level the sensor against the floor by segmenting the ground plane.

        Runs RANSAC on the latest world-frame cloud, iterating over the largest
        planes, keeps the near-vertical-normal (near-horizontal surface)
        candidate with the lowest centroid, and applies its tilt as a
        *residual* roll/pitch correction to the current pose. Yaw and position
        are preserved. Repeated calls converge to a flat floor.

        Mutually exclusive with IMU auto-level: raises when it is enabled.

        Args:
            distance_threshold: RANSAC inlier distance (cloud units, meters).
            max_planes: Max planes to segment while searching for the floor.
            min_inliers: Minimum inliers for a plane to be considered.
            verticality_threshold: Min ``|normal·up|`` to accept a plane as
                near-horizontal (0.7 ≈ 45° from vertical).

        Returns:
            The new Pose.

        Raises:
            ValueError: When IMU auto-level is on, no frame is cached yet, or
                no floor-like plane is found.
        """
        if self.imu_auto_level:
            raise ValueError("IMU auto-level is enabled; disable it before floor calibration.")

        points = self._latest_points
        if points is None or len(points) < min_inliers:
            raise ValueError("No point-cloud frame available yet.")

        import open3d as o3d
        from app.modules.lidar.core import plane_normal_to_roll_pitch

        up = np.array([0.0, 0.0, 1.0])
        xyz = np.asarray(points[:, :3], dtype=np.float64)
        remaining = o3d.geometry.PointCloud()
        remaining.points = o3d.utility.Vector3dVector(xyz)

        best_normal: Optional[np.ndarray] = None
        best_centroid_up = float("inf")

        for _ in range(max_planes):
            if len(remaining.points) < min_inliers:
                break
            plane_model, inliers = remaining.segment_plane(
                distance_threshold=distance_threshold,
                ransac_n=3,
                num_iterations=1000,
            )
            if len(inliers) < min_inliers:
                break

            normal = np.asarray(plane_model[:3], dtype=np.float64)
            n_norm = np.linalg.norm(normal)
            if n_norm > 0:
                normal = normal / n_norm
            if float(np.dot(normal, up)) < 0.0:
                normal = -normal

            inlier_pts = np.asarray(remaining.select_by_index(inliers).points)
            if abs(float(np.dot(normal, up))) >= verticality_threshold:
                centroid_up = float(inlier_pts.mean(axis=0) @ up)
                if centroid_up < best_centroid_up:
                    best_centroid_up = centroid_up
                    best_normal = normal

            remaining = remaining.select_by_index(inliers, invert=True)

        if best_normal is None:
            raise ValueError("No floor-like (near-horizontal) plane found.")

        d_roll, d_pitch = plane_normal_to_roll_pitch(best_normal, up)

        current = self.pose_params
        new_roll = max(-180.0, min(180.0, current.roll + d_roll))
        new_pitch = max(-180.0, min(180.0, current.pitch + d_pitch))
        new_pose = Pose(
            x=current.x,
            y=current.y,
            z=current.z,
            roll=new_roll,
            pitch=new_pitch,
            yaw=current.yaw,
        )

        self.set_pose(new_pose)

        from app.repositories.node_orm import NodeRepository
        NodeRepository().update_node_pose(self.id, new_pose)

        logger.info(
            f"[{self.id}] Floor calibration applied: "
            f"roll={new_roll:.2f}° pitch={new_pitch:.2f}° "
            f"(residual Δroll={d_roll:.2f}° Δpitch={d_pitch:.2f}°)"
        )
        return new_pose

    def emit_status(self) -> NodeStatusUpdate:
        """Return standardized status for this sensor node.
        
        Maps sensor lifecycle and connection state to OperationalState:
        - Process not alive → STOPPED
        - Process starting up → INITIALIZE
        - Connected and receiving frames → RUNNING
        - Connection error with last_error set → ERROR
        
        Returns:
            NodeStatusUpdate with operational_state and connection_status application_state
        """
        # Read runtime status from manager
        runtime_status = getattr(self.manager, 'node_runtime_status', {})
        runtime = runtime_status.get(self.id, {})

        connection_status = runtime.get("connection_status", "disconnected")
        last_error = runtime.get("last_error")
        process_alive = self._process.is_alive() if self._process else False

        # Determine operational state
        if not process_alive:
            operational_state = OperationalState.STOPPED
            app_value = "disconnected"
            app_color = "red"
        elif last_error:
            # Error state - process alive but connection failed
            operational_state = OperationalState.ERROR
            app_value = "disconnected"
            app_color = "red"
        elif connection_status == "starting":
            operational_state = OperationalState.INITIALIZE
            app_value = "starting"
            app_color = "orange"
        elif connection_status == "connected":
            operational_state = OperationalState.RUNNING
            app_value = "connected"
            app_color = "green"
        else:
            # Fallback: process alive but not connected yet
            operational_state = OperationalState.STOPPED
            app_value = "disconnected"
            app_color = "red"

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=operational_state,
            application_state=ApplicationState(
                label="connection_status",
                value=app_value,
                color=app_color,
            ),
            error_message=last_error,
            cycle_time_ms=round(self._cycle_time_ms, 1) if self._cycle_time_ms is not None else None,
        )
