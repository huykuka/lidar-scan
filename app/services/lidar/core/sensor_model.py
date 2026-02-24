"""
LiDAR sensor model representing configuration and state.
"""
from typing import Dict, Optional

import numpy as np

from app.pipeline import PointCloudPipeline
from .transformations import create_transformation_matrix, pose_to_dict


class LidarSensor:
    """Represents a single Lidar sensor and its processing pipeline configuration"""

    name: str
    topic_prefix: str

    def __init__(
        self,
        sensor_id: str,
        launch_args: str,
        pipeline: Optional[PointCloudPipeline] = None,
        pipeline_name: Optional[str] = None,
        mode: str = "real",
        pcd_path: Optional[str] = None,
        transformation: Optional[np.ndarray] = None,
        name: Optional[str] = None,
        topic_prefix: Optional[str] = None
    ):
        """
        Initialize a LiDAR sensor.
        
        Args:
            sensor_id: Unique identifier for the sensor
            launch_args: Launch arguments for real hardware mode
            pipeline: Optional processing pipeline instance
            pipeline_name: Name of the pipeline to use
            mode: Operating mode ("real" or "sim")
            pcd_path: Path to PCD file for simulation mode
            transformation: 4x4 transformation matrix (defaults to identity)
            name: Human-readable name (defaults to sensor_id)
            topic_prefix: WebSocket topic prefix (defaults to name)
        """
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
        self.pose_params: Dict[str, float] = {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}

    def set_pose(
        self,
        x: float,
        y: float,
        z: float,
        roll: float = 0,
        pitch: float = 0,
        yaw: float = 0
    ) -> "LidarSensor":
        """
        Sets the transformation matrix using translation (meters) and rotation (degrees).
        
        Args:
            x, y, z: Translation in meters
            roll, pitch, yaw: Rotation in degrees
        
        Returns:
            Self for method chaining
        """
        self.transformation = create_transformation_matrix(x, y, z, roll, pitch, yaw)
        self.pose_params = pose_to_dict(x, y, z, roll, pitch, yaw)
        return self

    def get_pose_params(self) -> Dict[str, float]:
        """
        Returns the current pose parameters.
        
        Returns:
            Dictionary with keys: x, y, z, roll, pitch, yaw
        """
        return self.pose_params.copy()
