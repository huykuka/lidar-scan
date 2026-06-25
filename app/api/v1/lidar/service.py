"""LiDAR endpoint handlers - Pure business logic without routing configuration."""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, ConfigDict

from app.modules.lidar.profiles import get_profile
from app.services.nodes.instance import node_manager


class LidarConfigValidationRequest(BaseModel):
    """Request model for LiDAR configuration validation"""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "lidar_type": "multiScan100",
                    "hostname": "192.168.1.10",
                    "udp_receiver_ip": "192.168.1.100",
                    "port": 2112,
                    "imu_udp_port": 7503
                },
                {
                    "lidar_type": "tiM-5xx",
                    "hostname": "192.168.1.11",
                    "port": 2112
                }
            ]
        }
    )

    lidar_type: str
    hostname: str
    udp_receiver_ip: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1024, le=65535)
    imu_udp_port: Optional[int] = Field(default=None, ge=1024, le=65535)


class LidarConfigValidationResponse(BaseModel):
    """Response model for LiDAR configuration validation"""
    valid: bool
    lidar_type: str
    resolved_launch_file: Optional[str]
    errors: List[str] = []
    warnings: List[str] = []


async def validate_lidar_config(request: LidarConfigValidationRequest) -> LidarConfigValidationResponse:
    """
    Validate a proposed LiDAR sensor configuration.
    
    Checks the configuration against the selected device model's requirements
    and returns validation results with any errors or warnings.
    """
    errors: List[str] = []
    warnings: List[str] = []
    resolved_launch_file: Optional[str] = None

    # Validate lidar_type
    try:
        profile = get_profile(request.lidar_type)
        resolved_launch_file = profile.launch_file
    except KeyError as e:
        # Use the detailed error message from get_profile which includes all valid models
        errors.append(str(e))
        return LidarConfigValidationResponse(
            valid=False,
            lidar_type=request.lidar_type,
            resolved_launch_file=None,
            errors=errors,
            warnings=warnings
        )

    # Validate hostname
    if not request.hostname or not request.hostname.strip():
        errors.append("Hostname is required and cannot be empty")

    # Validate UDP receiver IP for multiScan
    if profile.has_udp_receiver:
        if not request.udp_receiver_ip or not request.udp_receiver_ip.strip():
            errors.append("UDP receiver IP is required for multiScan devices")

    # Check port requirements and provide warnings
    if profile.port_arg:  # Device supports port configuration
        if request.port is None:
            warnings.append(f"No port specified; default port {profile.default_port} will be used")

    # Check IMU UDP port for multiScan
    if profile.has_imu_udp_port:
        if request.imu_udp_port is None:
            warnings.append("IMU UDP port not specified; IMU data will be disabled")

    # Return validation result
    is_valid = len(errors) == 0

    return LidarConfigValidationResponse(
        valid=is_valid,
        lidar_type=request.lidar_type,
        resolved_launch_file=resolved_launch_file,
        errors=errors,
        warnings=warnings
    )


def _get_lidar_sensor(node_id: str):
    """Resolve a LidarSensor from the node manager, raising 404/400 on failure."""
    from app.modules.lidar.node import LidarSensor

    node = node_manager.nodes.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    if not isinstance(node, LidarSensor):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} is not a LiDAR sensor (type: {type(node).__name__})",
        )
    return node


async def calibrate_from_imu(node_id: str) -> Dict[str, Any]:
    """Apply IMU-derived roll/pitch to the sensor pose and persist.

    Reads the latest IMU gravity vector, computes the tilt correction,
    writes the updated pose to the database, and hot-updates the
    in-memory transformation matrix.

    Returns:
        Dict with new pose values and the IMU snapshot used.
    """
    sensor = _get_lidar_sensor(node_id)

    new_pose = sensor.calibrate_from_imu()
    if new_pose is None:
        raise HTTPException(
            status_code=409,
            detail="No IMU data available yet — sensor may not have started or does not support IMU.",
        )

    # Hot-update the in-memory transformation so subsequent frames use the new pose
    await node_manager.hot_update_node_pose(node_id)

    return {
        "success": True,
        "node_id": node_id,
        "pose": new_pose.to_flat_dict(),
        "imu": sensor.latest_imu.to_dict() if sensor.latest_imu else None,
    }


async def get_imu_status(node_id: str) -> Dict[str, Any]:
    """Return the latest IMU reading and auto-level state for a sensor node."""
    sensor = _get_lidar_sensor(node_id)

    return {
        "node_id": node_id,
        "imu_auto_level": sensor.imu_auto_level,
        "has_imu_data": sensor.latest_imu is not None,
        "imu": sensor.latest_imu.to_dict() if sensor.latest_imu else None,
    }
