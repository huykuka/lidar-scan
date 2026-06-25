"""LiDAR router configuration and endpoint metadata."""

from fastapi import APIRouter

from .service import (
    calibrate_from_imu,
    get_imu_status,
    validate_lidar_config,
    LidarConfigValidationRequest, LidarConfigValidationResponse
)

# Router configuration
router = APIRouter(prefix="/lidar", tags=["LiDAR"])


@router.post(
    "/validate-lidar-config",
    response_model=LidarConfigValidationResponse,
    responses={400: {"description": "Invalid LiDAR configuration"}, 404: {"description": "LiDAR type not found"}},
    summary="Validate LiDAR Configuration",
    description="Validate a proposed LiDAR sensor configuration against device model requirements.",
)
async def lidar_validate_endpoint(request: LidarConfigValidationRequest):
    return await validate_lidar_config(request)


@router.post(
    "/{node_id}/calibrate-from-imu",
    responses={
        404: {"description": "Sensor node not found"},
        400: {"description": "Node is not a LiDAR sensor"},
        409: {"description": "No IMU data available yet"},
    },
    summary="Calibrate Sensor Pose from IMU",
    description="Snapshot the current IMU gravity reading, compute roll/pitch, "
                "apply to the sensor pose, and persist to the database.",
)
async def lidar_calibrate_from_imu_endpoint(node_id: str):
    return await calibrate_from_imu(node_id)


@router.get(
    "/{node_id}/imu-status",
    responses={
        404: {"description": "Sensor node not found"},
        400: {"description": "Node is not a LiDAR sensor"},
    },
    summary="Get IMU Status",
    description="Return latest IMU reading and auto-level state for a sensor node.",
)
async def lidar_imu_status_endpoint(node_id: str):
    return await get_imu_status(node_id)
