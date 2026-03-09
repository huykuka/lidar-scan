"""
LiDAR-specific API endpoints.

Provides device profile information and configuration validation for SICK LiDAR models.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict

from app.modules.lidar.profiles import get_enabled_profiles, get_profile

router = APIRouter(prefix="/lidar", tags=["LiDAR"])


# --- Pydantic Models ---

class SickLidarProfileResponse(BaseModel):
    """Response model for a single SICK LiDAR device profile"""
    model_id: str
    display_name: str
    launch_file: str
    default_hostname: str
    port_arg: str           # "port" | "udp_port" | ""
    default_port: int
    has_udp_receiver: bool
    has_imu_udp_port: bool
    scan_layers: int
    # Backend-controlled UI elements
    thumbnail_url: Optional[str] = None     # URL to device thumbnail image
    icon_name: Optional[str] = None         # Synergy UI icon name
    icon_color: Optional[str] = None        # Hex color for icon (e.g., "#FF6B35")


class ProfilesListResponse(BaseModel):
    """Response model for the list of all supported LiDAR profiles"""
    profiles: List[SickLidarProfileResponse]


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


# --- API Endpoints ---

@router.get("/profiles", response_model=ProfilesListResponse)
async def get_lidar_profiles():
    """
    Get all enabled SICK LiDAR device profiles for frontend dropdown.
    
    Returns only enabled models (excludes disabled models like LD-MRS).
    This is a pure in-memory operation with no database or file system access.
    """
    profiles = get_enabled_profiles()
    
    profile_responses = [
        SickLidarProfileResponse(
            model_id=profile.model_id,
            display_name=profile.display_name,
            launch_file=profile.launch_file,
            default_hostname=profile.default_hostname,
            port_arg=profile.port_arg,
            default_port=profile.default_port,
            has_udp_receiver=profile.has_udp_receiver,
            has_imu_udp_port=profile.has_imu_udp_port,
            scan_layers=profile.scan_layers,
            thumbnail_url=profile.thumbnail_url,
            icon_name=profile.icon_name,
            icon_color=profile.icon_color
        )
        for profile in profiles
    ]
    
    return ProfilesListResponse(profiles=profile_responses)


@router.post("/validate-lidar-config", response_model=LidarConfigValidationResponse, responses={400: {"description": "Invalid LiDAR configuration"}, 404: {"description": "LiDAR type not found"}})
async def validate_lidar_config(request: LidarConfigValidationRequest):
    """
    Validate a proposed LiDAR sensor configuration.
    
    Checks the configuration against the selected device model's requirements
    and returns validation results with any errors or warnings.
    """
    errors = []
    warnings = []
    resolved_launch_file = None
    
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