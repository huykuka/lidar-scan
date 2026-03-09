"""LiDAR router configuration and endpoint metadata."""

from fastapi import APIRouter
from .service import (
    get_lidar_profiles, validate_lidar_config,
    ProfilesListResponse, LidarConfigValidationRequest, LidarConfigValidationResponse
)


# Router configuration
router = APIRouter(prefix="/lidar", tags=["LiDAR"])

# Endpoint configurations
@router.get(
    "/profiles",
    response_model=ProfilesListResponse,
    summary="Get LiDAR Profiles",
    description="Get all enabled SICK LiDAR device profiles for frontend dropdown. Pure in-memory operation with no database or file system access.",
)
async def lidar_profiles_endpoint():
    return await get_lidar_profiles()


@router.post(
    "/validate-lidar-config",
    response_model=LidarConfigValidationResponse,
    responses={400: {"description": "Invalid LiDAR configuration"}, 404: {"description": "LiDAR type not found"}},
    summary="Validate LiDAR Configuration",
    description="Validate a proposed LiDAR sensor configuration against device model requirements.",
)
async def lidar_validate_endpoint(request: LidarConfigValidationRequest):
    return await validate_lidar_config(request)