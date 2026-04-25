"""LiDAR router configuration and endpoint metadata."""

from fastapi import APIRouter
from .service import (
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
