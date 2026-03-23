"""
Calibration node for ICP-based LiDAR sensor alignment.

This module provides the main CalibrationNode class that orchestrates
the calibration workflow within the DAG system.

Provenance Tracking:
- source_sensor_id: Canonical leaf LidarSensor node ID (from payload['lidar_id'])
- node_id: Last processing node that forwarded the payload
- processing_chain: Ordered list of DAG node IDs from leaf sensor to calibration node
"""
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
from collections import deque
import numpy as np
import uuid

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.schemas.pose import Pose
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change
from app.repositories.node_orm import NodeRepository
from app.db.session import SessionLocal
from app.modules.lidar.core.transformations import (
    create_transformation_matrix,
    pose_to_dict
)
from .registration.icp_engine import ICPEngine
from .history import CalibrationHistory, create_calibration_record

logger = get_logger(__name__)


@dataclass
class BufferedFrame:
    """
    Frame buffer entry with provenance metadata.
    
    Stores point cloud data along with source sensor ID and processing chain
    to enable correct transformation patching on complex DAG topologies.
    """
    points: np.ndarray           # (N, 3+) point cloud
    timestamp: float             # Unix epoch
    source_sensor_id: str        # Canonical leaf sensor ID (lidar_id)
    processing_chain: List[str]  # Full DAG path: [sensor, crop, downsample, ...]
    node_id: str                 # Last processing node that forwarded this payload


def extract_pose_from_matrix(T: np.ndarray) -> "Pose":
    """
    Extract 6-DOF pose (x, y, z, roll, pitch, yaw) from 4x4 transformation matrix.
    
    Args:
        T: 4x4 transformation matrix
        
    Returns:
        Pose instance with angles in degrees, clamped to [-180, +180].
    """
    import math
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
    
    def _clamp_angle(deg: float) -> float:
        """Clamp angle to [-180, +180] range."""
        deg = deg % 360.0
        if deg > 180.0:
            deg -= 360.0
        return deg

    return Pose(
        x=float(x),
        y=float(y),
        z=float(z),
        roll=_clamp_angle(float(np.degrees(roll))),
        pitch=_clamp_angle(float(np.degrees(pitch))),
        yaw=_clamp_angle(float(np.degrees(yaw))),
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
        
        # Calibration state - REFACTORED: Ring-buffer with provenance tracking
        self._frame_buffer: Dict[str, deque] = {}  # {source_sensor_id: deque[BufferedFrame]}
        self._max_frames = config.get("max_buffered_frames", 30)
        # Configured reference sensor (from node editor). When set, role assignment
        # in on_input is deterministic: this sensor is always reference, everything
        # else is always source. When None, falls back to first-arrived heuristic.
        self._configured_reference_id: Optional[str] = config.get("reference_sensor_id") or None
        self._reference_sensor_id: Optional[str] = self._configured_reference_id
        self._source_sensor_ids: List[str] = []
        self._pending_calibration: Optional[Dict[str, Any]] = None
        self._last_calibration_time: Optional[str] = None
        
        # Configuration
        self.auto_save = config.get("auto_save", False)
        self.min_fitness_to_save = config.get("min_fitness_to_save", 0.8)
        
        self._enabled = True
    
    async def on_input(self, payload: Dict[str, Any]):
        """
        Store incoming point clouds in ring-buffer with provenance metadata.
        
        This method is called by NodeManager when upstream nodes send data.
        
        Args:
            payload: Data payload with keys:
                - lidar_id: Canonical leaf sensor ID (REQUIRED for provenance)
                - node_id: Last processing node that forwarded this payload
                - points: (N, 3+) numpy array
                - timestamp: Frame timestamp
                - processing_chain: List of node IDs from leaf sensor to here
        """
        if not self._enabled:
            return
        
        # Canonical sensor ID is always lidar_id (set at the hardware source)
        # node_id is the last processing node — use it for DAG routing only
        source_sensor_id = payload.get("lidar_id")
        node_id = payload.get("node_id") or source_sensor_id or ""
        points = payload.get("points")
        timestamp = payload.get("timestamp", 0.0)
        processing_chain = [str(x) for x in (payload.get("processing_chain") or [node_id or source_sensor_id]) if x is not None]
        
        logger.debug(f"[{self.id}] on_input: source_sensor_id={source_sensor_id}, "
                    f"node_id={node_id}, chain={processing_chain}, points={len(points) if points is not None else 'None'}")
        
        if source_sensor_id and points is not None and len(points) > 0:
            # Initialize buffer for this source sensor
            if source_sensor_id not in self._frame_buffer:
                self._frame_buffer[source_sensor_id] = deque(maxlen=self._max_frames)
            
            # Create buffered frame with provenance
            frame = BufferedFrame(
                points=points.copy(),
                timestamp=timestamp,
                source_sensor_id=source_sensor_id,
                processing_chain=processing_chain,
                node_id=node_id
            )
            self._frame_buffer[source_sensor_id].append(frame)
            
            # Role assignment:
            # - If reference_sensor_id was configured by the user, it is fixed and
            #   every other sensor is a source (regardless of arrival order).
            # - If no reference was configured, fall back to first-arrived heuristic.
            if self._configured_reference_id:
                # User-defined reference: deterministic assignment
                if source_sensor_id != self._configured_reference_id:
                    if source_sensor_id not in self._source_sensor_ids:
                        self._source_sensor_ids.append(source_sensor_id)
                        logger.info(f"[{self.id}] Added source sensor: {source_sensor_id[:8]}. "
                                   f"Total sources: {len(self._source_sensor_ids)}")
            else:
                # Auto heuristic: first seen = reference, rest = sources
                if self._reference_sensor_id is None:
                    self._reference_sensor_id = source_sensor_id
                    logger.info(f"[{self.id}] Auto-set reference sensor: {source_sensor_id[:8]}")
                elif (source_sensor_id not in self._source_sensor_ids
                      and source_sensor_id != self._reference_sensor_id):
                    self._source_sensor_ids.append(source_sensor_id)
                    logger.info(f"[{self.id}] Added source sensor: {source_sensor_id[:8]}. "
                               f"Total sources: {len(self._source_sensor_ids)}")
        
        # Forward data through (passthrough mode)
        await self.manager.forward_data(self.id, payload)
    
    def _aggregate_frames(
        self,
        source_sensor_id: str,
        sample_frames: int
    ) -> Optional[Tuple[np.ndarray, str, List[str]]]:
        """
        Aggregate up to sample_frames recent frames for source_sensor_id.
        
        Args:
            source_sensor_id: Canonical leaf sensor ID
            sample_frames: Number of recent frames to aggregate
            
        Returns:
            Tuple of (aggregated_points, source_sensor_id, latest_processing_chain)
            or None if no frames available.
        """
        buf = self._frame_buffer.get(source_sensor_id)
        if not buf:
            return None
        
        frames = list(buf)[-sample_frames:]  # most recent N frames
        if not frames:
            return None
        
        aggregated = np.concatenate([f.points for f in frames], axis=0)
        latest_chain = frames[-1].processing_chain
        return aggregated, source_sensor_id, latest_chain
    
    async def trigger_calibration(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        User-triggered calibration action with provenance tracking.
        
        This method is called from the API endpoint when user clicks "Run Calibration".
        
        Args:
            params: Calibration parameters:
                - reference_sensor_id: Optional override for reference sensor
                - source_sensor_ids: Optional list of sensors to calibrate
                - sample_frames: Number of frames to aggregate (default: 5)
                
        Returns:
            Dict with:
                - success: bool
                - run_id: str (correlates multi-sensor runs)
                - results: Dict[sensor_id, calibration_result]
                - pending_approval: bool
                - error: str (if success=False)
        """
        # Determine reference sensor
        ref_id = params.get("reference_sensor_id") or self._reference_sensor_id
        if not ref_id or ref_id not in self._frame_buffer:
            return {
                "success": False,
                "error": f"Reference sensor {ref_id} has no buffered data"
            }
        
        # Aggregate reference frames
        sample_frames = params.get("sample_frames", 5)
        ref_aggregated = self._aggregate_frames(ref_id, sample_frames)
        if not ref_aggregated:
            return {
                "success": False,
                "error": f"Cannot aggregate frames for reference sensor {ref_id}"
            }
        ref_points, _, _ = ref_aggregated
        
        # Determine source sensors to calibrate
        source_ids = params.get("source_sensor_ids") or self._source_sensor_ids
        if not source_ids:
            return {
                "success": False,
                "error": "No source sensors to calibrate"
            }
        
        # Generate run_id for this calibration run
        run_id = uuid.uuid4().hex[:12]
        
        # Run ICP for each source sensor
        results = {}
        calibration_records = {}
        for source_id in source_ids:
            # Aggregate frames for source sensor
            source_aggregated = self._aggregate_frames(source_id, sample_frames)
            if not source_aggregated:
                logger.warning(f"Cannot aggregate frames for source sensor {source_id}")
                continue
            
            source_points, source_sensor_id, processing_chain = source_aggregated
            
            # CRITICAL: Get current sensor pose from database using source_sensor_id (leaf sensor)
            # NOT node_id (which may be an intermediate processing node)
            repo = NodeRepository()
            sensor_node_data = repo.get_by_id(source_sensor_id)
            if not sensor_node_data:
                logger.warning(f"Sensor node {source_sensor_id} not found in database")
                continue
            
            config = sensor_node_data.get('config', {})
            
            # Read pose from the nested pose sub-object (B-06 canonical format)
            raw_pose = sensor_node_data.get("pose") or {}
            current_pose = Pose(
                x=raw_pose.get("x", 0.0),
                y=raw_pose.get("y", 0.0),
                z=raw_pose.get("z", 0.0),
                roll=raw_pose.get("roll", 0.0),
                pitch=raw_pose.get("pitch", 0.0),
                yaw=raw_pose.get("yaw", 0.0),
            )
            
            # Build initial transformation from current pose
            T_current = create_transformation_matrix(**current_pose.to_flat_dict())

            # Detect whether this sensor has a previously accepted calibrated pose.
            # Point clouds arriving here are already in world frame (LidarSensor
            # applies self.transformation before forwarding), so when a prior pose
            # exists the source cloud is already approximately aligned with the
            # reference.  We pass has_prior_pose to the engine so it can skip the
            # FPFH/RANSAC global stage — it would only degrade an already-close init.
            has_prior_pose = not np.allclose(T_current, np.eye(4), atol=1e-6)

            # Run ICP registration.
            # ICP init is always np.eye(4) because the points are world-frame; the
            # prior pose is implicitly encoded in the already-transformed clouds.
            reg_result = await self.icp_engine.register(
                source=source_points,
                target=ref_points,
                has_prior_pose=has_prior_pose,
            )

            # Compose: T_new = T_icp_delta @ T_current
            T_new = reg_result.transformation @ T_current
            
            # Extract new pose
            new_pose = extract_pose_from_matrix(T_new)
            
            # Create calibration record with provenance
            record = create_calibration_record(
                sensor_id=source_sensor_id,
                source_sensor_id=source_sensor_id,
                processing_chain=processing_chain,
                run_id=run_id,
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
            
            calibration_records[source_sensor_id] = record
            
            # Auto-save if enabled and quality threshold met
            auto_saved = False
            if self.auto_save and reg_result.fitness >= self.min_fitness_to_save:
                await self._apply_calibration(source_sensor_id, record)
                record.accepted = True
                auto_saved = True
            
            results[source_sensor_id] = {
                "fitness": reg_result.fitness,
                "rmse": reg_result.rmse,
                "quality": reg_result.quality,
                "stages_used": reg_result.stages_used,
                "pose_before": current_pose.to_flat_dict(),
                "pose_after": new_pose.to_flat_dict(),
                "auto_saved": auto_saved,
                "source_sensor_id": source_sensor_id,
                "processing_chain": processing_chain
            }
        
        # Store pending calibrations (for user approval)
        self._pending_calibration = calibration_records
        self._last_calibration_time = datetime.now(timezone.utc).isoformat()
        notify_status_change(self.id)

        return {
            "success": True,
            "run_id": run_id,
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

        # Clear pending so next trigger starts fresh and status returns to idle
        self._pending_calibration = None
        notify_status_change(self.id)

        return {"success": True, "accepted": sensors_to_accept}
    
    async def reject_calibration(self) -> Dict[str, Any]:
        """
        User rejects pending calibration (no changes applied).
        
        Returns:
            Dict with success status
        """
        self._pending_calibration = None
        notify_status_change(self.id)
        return {"success": True}
    
    async def _apply_calibration(self, sensor_id: str, record, db_session=None):
        """
        Apply calibration: update sensor config + save history.
        
        CRITICAL: Always updates the leaf LidarSensor node (source_sensor_id),
        NOT an intermediate processing node. This ensures the transformation
        is picked up by LidarSensor.handle_data() after reload_config().
        
        Args:
            sensor_id: Sensor node ID (for backward compatibility, but overridden by source_sensor_id)
            record: CalibrationRecord to apply
            db_session: Optional SQLAlchemy session
        """
        # Get or create database session
        db = db_session or SessionLocal()
        
        try:
            # CRITICAL: Always update the leaf LidarSensor node (source_sensor_id),
            # NOT an intermediate processing node. This ensures the transformation
            # is picked up by LidarSensor.handle_data() after reload_config().
            target_id = getattr(record, "source_sensor_id", None) or sensor_id
            
            # Load the existing full config so we don't wipe non-pose fields
            # (mode, hostname, lidar_type, pcd_path, etc.)
            repo = NodeRepository(session=db)
            existing_node = repo.get_by_id(target_id)
            if not existing_node:
                raise ValueError(f"Sensor node {target_id} not found in database")
            
            # Write pose as nested entity via update_node_pose — never flat keys
            pose_after = record.pose_after
            if isinstance(pose_after, Pose):
                pose_to_write = pose_after
            else:
                # Legacy dict support (CalibrationRecord.pose_after still typed Dict in history)
                pose_to_write = Pose(**pose_after)
            repo.update_node_pose(target_id, pose_to_write)
            
            # Save to calibration history, passing node_id for provenance
            now_iso = datetime.now(timezone.utc).isoformat()
            new_record_id = CalibrationHistory.save_record(record, db_session=db, node_id=self.id)
            
            # Mark the new history record as accepted with timestamp
            from app.repositories import calibration_orm
            calibration_orm.update_calibration_acceptance(
                db=db,
                record_id=new_record_id,
                accepted=True,
                accepted_at=now_iso,
            )
            
            # Trigger NodeManager reload to apply new transforms
            await self.manager.reload_config()
        finally:
            if db_session is None:
                db.close()

    def get_calibration_status(self) -> Dict[str, Any]:
        """
        Return full calibration workflow state for the polling endpoint.

        Unlike emit_status() which is for WebSocket broadcast, this returns
        the complete state needed by the calibration page. This method is
        a pure read — it does NOT modify any state.

        Returns:
            Dict with calibration_state, pending_results, quality metrics, etc.
        """
        calibration_state = "pending" if self._pending_calibration is not None else "idle"

        pending_results: Dict[str, Any] = {}
        if self._pending_calibration:
            for sensor_id, record in self._pending_calibration.items():
                pending_results[sensor_id] = {
                    "fitness": record.fitness,
                    "rmse": record.rmse,
                    "quality": record.quality,
                    "quality_good": record.fitness >= self.min_fitness_to_save,
                    "source_sensor_id": record.source_sensor_id,
                    "processing_chain": list(record.processing_chain or []),
                    "pose_before": record.pose_before.to_flat_dict(),
                    "pose_after": record.pose_after.to_flat_dict(),
                    "transformation_matrix": record.transformation_matrix,
                }

        quality_good: Optional[bool] = None
        if self._pending_calibration:
            quality_good = all(
                r.fitness >= self.min_fitness_to_save
                for r in self._pending_calibration.values()
            )

        return {
            "node_id": self.id,
            "node_name": self.name,
            "enabled": self._enabled,
            "calibration_state": calibration_state,
            "quality_good": quality_good,
            "reference_sensor_id": self._reference_sensor_id,
            "source_sensor_ids": list(self._source_sensor_ids),
            "buffered_frames": {k: len(v) for k, v in self._frame_buffer.items()},
            "last_calibration_time": self._last_calibration_time,
            "pending_results": pending_results,
        }

    def emit_status(self) -> NodeStatusUpdate:
        """Return standardised status for this calibration node.

        Maps enabled flag and pending-calibration state to OperationalState:
        - ``_enabled == False`` → STOPPED, calibrating=False, gray
        - ``_enabled == True``, no pending calibration → RUNNING, calibrating=False, gray
        - ``_enabled == True``, pending calibration present → RUNNING, calibrating=True, blue

        Returns:
            NodeStatusUpdate with operational_state and calibrating application_state
        """
        if not self._enabled:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.STOPPED,
                application_state=ApplicationState(
                    label="calibrating",
                    value=False,
                    color="gray",
                ),
            )

        calibrating = self._pending_calibration is not None
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="calibrating",
                value=calibrating,
                color="blue" if calibrating else "gray",
            ),
        )

    def enable(self):
        """Activate calibration node"""
        self._enabled = True
        notify_status_change(self.id)

    def disable(self):
        """Deactivate calibration node"""
        self._enabled = False
        notify_status_change(self.id)
