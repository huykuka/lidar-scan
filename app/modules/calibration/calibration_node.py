"""
Calibration node for ICP-based LiDAR sensor alignment.

This module provides the main CalibrationNode class that orchestrates
the calibration workflow within the DAG system.
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
import numpy as np

from app.core.logging import get_logger
from app.services.nodes.base_module import ModuleNode

logger = get_logger(__name__)
from app.modules.lidar.core.transformations import (
    create_transformation_matrix,
    pose_to_dict
)
from .registration.icp_engine import ICPEngine
from .history import CalibrationHistory, create_calibration_record


def extract_pose_from_matrix(T: np.ndarray) -> Dict[str, float]:
    """
    Extract 6-DOF pose (x, y, z, roll, pitch, yaw) from 4x4 transformation matrix.
    
    Args:
        T: 4x4 transformation matrix
        
    Returns:
        Dictionary with keys: x, y, z, roll, pitch, yaw (angles in degrees)
    """
    # Translation
    x, y, z = T[:3, 3]
    
    # Rotation matrix decomposition (ZYX Euler angles)
    R = T[:3, :3]
    
    # Extract Euler angles (in radians)
    # pitch (rotation around Y axis)
    pitch = np.arctan2(-R[2, 0], np.sqrt(R[0, 0]**2 + R[1, 0]**2))
    
    # Handle gimbal lock
    if np.abs(np.cos(pitch)) > 1e-6:
        # yaw (rotation around Z axis)
        yaw = np.arctan2(R[1, 0], R[0, 0])
        # roll (rotation around X axis)
        roll = np.arctan2(R[2, 1], R[2, 2])
    else:
        # Gimbal lock case
        yaw = 0.0
        roll = np.arctan2(-R[1, 2], R[1, 1])
    
    # Convert radians to degrees
    return pose_to_dict(
        x=float(x),
        y=float(y),
        z=float(z),
        roll=float(np.degrees(roll)),
        pitch=float(np.degrees(pitch)),
        yaw=float(np.degrees(yaw))
    )


class CalibrationNode(ModuleNode):
    """
    ICP Calibration Node - Aligns multiple LiDAR sensors.
    
    Workflow:
    1. Buffer incoming point clouds from connected sensors
    2. Wait for user to trigger calibration action
    3. Run ICP to compute transformation
    4. Store results pending user approval
    5. User accepts/rejects calibration
    6. If accepted: update sensor pose configs and reload DAG
    """
    
    def __init__(self, manager, node_id: str, config: Dict[str, Any]):
        """
        Initialize calibration node.
        
        Args:
            manager: NodeManager instance
            node_id: Unique node identifier
            config: Node configuration dict
        """
        self.manager = manager
        self.id = node_id
        self.name = config.get("name", "ICP Calibration")
        
        # ICP engine
        self.icp_engine = ICPEngine(config)
        
        # Calibration state
        self._latest_frames: Dict[str, np.ndarray] = {}  # {node_id: points}
        self._reference_sensor_id: Optional[str] = None
        self._source_sensor_ids: List[str] = []
        self._pending_calibration: Optional[Dict[str, Any]] = None
        self._last_calibration_time: Optional[str] = None
        
        # Configuration
        self.auto_save = config.get("auto_save", False)
        self.min_fitness_to_save = config.get("min_fitness_to_save", 0.8)
        
        self._enabled = True
    
    async def on_input(self, payload: Dict[str, Any]):
        """
        Store incoming point clouds in buffer.
        
        This method is called by NodeManager when upstream nodes send data.
        
        Args:
            payload: Data payload with keys:
                - node_id OR lidar_id: Source node ID (lidar_id from sensors, node_id from other nodes)
                - points: (N, 3+) numpy array
                - timestamp: Frame timestamp
        """
        if not self._enabled:
            return
        
        # Accept either lidar_id (from sensor workers) or node_id (from other nodes)
        source_id = payload.get("lidar_id") or payload.get("node_id")
        points = payload.get("points")
        
        logger.debug(f"[{self.id}] on_input called: source_id={source_id}, points={'None' if points is None else len(points)}")
        
        if source_id and points is not None and len(points) > 0:
            # Store latest frame from this sensor
            self._latest_frames[source_id] = points
            
            # Determine reference sensor (first sensor by default)
            if self._reference_sensor_id is None:
                self._reference_sensor_id = source_id
                logger.info(f"[{self.id}] Set reference sensor: {source_id[:8]}")
            elif source_id not in self._source_sensor_ids and source_id != self._reference_sensor_id:
                self._source_sensor_ids.append(source_id)
                logger.info(f"[{self.id}] Added source sensor: {source_id[:8]}. Total sources: {len(self._source_sensor_ids)}")
        
        # Forward data through (passthrough mode)
        await self.manager.forward_data(self.id, payload)
    
    async def trigger_calibration(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        User-triggered calibration action.
        
        This method is called from the API endpoint when user clicks "Run Calibration".
        
        Args:
            params: Calibration parameters:
                - reference_sensor_id: Optional override for reference sensor
                - source_sensor_ids: Optional list of sensors to calibrate
                
        Returns:
            Dict with:
                - success: bool
                - results: Dict[sensor_id, calibration_result]
                - pending_approval: bool
                - error: str (if success=False)
        """
        from app.repositories.node_orm import NodeRepository
        
        # Determine reference sensor
        ref_id = params.get("reference_sensor_id") or self._reference_sensor_id
        if not ref_id or ref_id not in self._latest_frames:
            return {
                "success": False,
                "error": f"Reference sensor {ref_id} has no buffered data"
            }
        
        ref_points = self._latest_frames[ref_id]
        
        # Determine source sensors to calibrate
        source_ids = params.get("source_sensor_ids") or self._source_sensor_ids
        if not source_ids:
            return {
                "success": False,
                "error": "No source sensors to calibrate"
            }
        
        # Run ICP for each source sensor
        results = {}
        calibration_records = {}
        
        for source_id in source_ids:
            if source_id not in self._latest_frames:
                continue
            
            source_points = self._latest_frames[source_id]
            
            # Get current sensor pose from database
            repo = NodeRepository()
            sensor_node_data = repo.get_by_id(source_id)
            if not sensor_node_data:
                continue
            
            config = sensor_node_data.get('config', {})
            
            current_pose = pose_to_dict(
                x=config.get("x", 0.0),
                y=config.get("y", 0.0),
                z=config.get("z", 0.0),
                roll=config.get("roll", 0.0),
                pitch=config.get("pitch", 0.0),
                yaw=config.get("yaw", 0.0)
            )
            
            # Build initial transformation from current pose
            T_current = create_transformation_matrix(**current_pose)
            
            # Run ICP registration
            reg_result = await self.icp_engine.register(
                source=source_points,
                target=ref_points,
                initial_transform=T_current
            )
            
            # Compose transformations: T_new = T_icp @ T_current
            T_new = reg_result.transformation @ T_current
            
            # Extract new pose
            new_pose = extract_pose_from_matrix(T_new)
            
            # Create calibration record
            record = create_calibration_record(
                sensor_id=source_id,
                reference_sensor_id=ref_id,
                fitness=reg_result.fitness,
                rmse=reg_result.rmse,
                quality=reg_result.quality,
                stages_used=reg_result.stages_used,
                pose_before=current_pose,
                pose_after=new_pose,
                transformation_matrix=T_new.tolist(),
                accepted=False
            )
            
            calibration_records[source_id] = record
            
            # Auto-save if enabled and quality threshold met
            auto_saved = False
            if self.auto_save and reg_result.fitness >= self.min_fitness_to_save:
                await self._apply_calibration(source_id, record)
                record.accepted = True
                auto_saved = True
            
            results[source_id] = {
                "fitness": reg_result.fitness,
                "rmse": reg_result.rmse,
                "quality": reg_result.quality,
                "stages_used": reg_result.stages_used,
                "pose_before": current_pose,
                "pose_after": new_pose,
                "auto_saved": auto_saved
            }
        
        # Store pending calibrations (for user approval)
        self._pending_calibration = calibration_records
        self._last_calibration_time = datetime.utcnow().isoformat()
        
        return {
            "success": True,
            "results": results,
            "pending_approval": not self.auto_save
        }
    
    async def accept_calibration(self, sensor_ids: Optional[List[str]] = None, db=None) -> Dict[str, Any]:
        """
        User accepts pending calibration and saves to database.
        
        Args:
            sensor_ids: Specific sensors to accept (None = all pending)
            db: Optional SQLAlchemy session
            
        Returns:
            Dict with success status and accepted sensor IDs
        """
        if not self._pending_calibration:
            return {"success": False, "error": "No pending calibration"}
        
        sensors_to_accept = sensor_ids or list(self._pending_calibration.keys())
        
        for sensor_id in sensors_to_accept:
            if sensor_id in self._pending_calibration:
                record = self._pending_calibration[sensor_id]
                await self._apply_calibration(sensor_id, record, db_session=db)
                record.accepted = True
        
        return {"success": True, "accepted": sensors_to_accept}
    
    async def reject_calibration(self) -> Dict[str, Any]:
        """
        User rejects pending calibration (no changes applied).
        
        Returns:
            Dict with success status
        """
        self._pending_calibration = None
        return {"success": True}
    
    async def _apply_calibration(self, sensor_id: str, record, db_session=None):
        """
        Apply calibration: update sensor config + save history.
        
        Args:
            sensor_id: Sensor node ID
            record: CalibrationRecord to apply
            db_session: Optional SQLAlchemy session
        """
        from app.repositories.node_orm import NodeRepository
        from app.db.session import SessionLocal
        
        # Get or create database session
        db = db_session or SessionLocal()
        
        try:
            # Update sensor pose in database
            repo = NodeRepository(session=db)
            repo.update_node_config(sensor_id, {
                "x": record.pose_after["x"],
                "y": record.pose_after["y"],
                "z": record.pose_after["z"],
                "roll": record.pose_after["roll"],
                "pitch": record.pose_after["pitch"],
                "yaw": record.pose_after["yaw"]
            })
            
            # Save to calibration history
            CalibrationHistory.save_record(record, db_session=db)
            
            # Trigger NodeManager reload to apply new transforms
            self.manager.reload_config()
        finally:
            if db_session is None:
                db.close()
    
    def get_status(self, runtime_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Returns calibration node status + latest results.
        
        Args:
            runtime_status: Optional runtime status dict
            
        Returns:
            Status dict with calibration state
        """
        status = {
            "id": self.id,
            "name": self.name,
            "type": "calibration",
            "enabled": self._enabled,
            "reference_sensor": self._reference_sensor_id,
            "source_sensors": self._source_sensor_ids,
            "buffered_frames": list(self._latest_frames.keys()),
            "last_calibration_time": self._last_calibration_time,
            "has_pending": self._pending_calibration is not None,
            "pending_results": {}
        }
        
        if self._pending_calibration:
            status["pending_results"] = {
                sensor_id: {
                    "fitness": record.fitness,
                    "rmse": record.rmse,
                    "quality": record.quality
                }
                for sensor_id, record in self._pending_calibration.items()
            }
        
        return status
    
    def enable(self):
        """Activate calibration node"""
        self._enabled = True
    
    def disable(self):
        """Deactivate calibration node"""
        self._enabled = False
