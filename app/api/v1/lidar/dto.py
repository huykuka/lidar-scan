"""LiDAR DTOs - Data Transfer Objects for request/response serialization."""

from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


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
