"""
LiDAR device profiles for multi-model support.

This is a pure data module containing SICK LiDAR device definitions and configuration.
No FastAPI, I/O, or Open3D dependencies - stdlib only.
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SickLidarProfile:
    """Profile definition for a SICK LiDAR device model"""
    model_id: str  # canonical key used as the `lidar_type` config value
    display_name: str  # shown in UI dropdown label
    launch_file: str  # relative path from repo root, e.g. "launch/sick_tim_5xx.launch"
    default_hostname: str  # default IP for this device family
    port_arg: str  # the arg name to pass to the launch file: "port", "udp_port", or ""
    default_port: int  # default port value (0 if port_arg is empty)
    has_udp_receiver: bool  # True only for multiScan (controls udp_receiver_ip arg emission)
    has_imu_udp_port: bool  # True only for multiScan (controls imu_udp_port arg emission)
    scan_layers: int  # informational: 1 = 2D, >1 = multi-layer


# Registry of all supported SICK LiDAR models
_PROFILES = {
    "multiscan": SickLidarProfile(
        model_id="multiscan",
        display_name="SICK multiScan",
        launch_file="launch/sick_multiscan.launch",
        default_hostname="192.168.100.124",
        port_arg="udp_port",
        default_port=2115,
        has_udp_receiver=True,
        has_imu_udp_port=True,
        scan_layers=16
    ),
    "tim_2xx": SickLidarProfile(
        model_id="tim_2xx",
        display_name="SICK TiM2xx",
        launch_file="launch/sick_tim_240.launch",
        default_hostname="192.168.1.11",
        port_arg="port",
        default_port=2112,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1
    ),
    "tim_4xx": SickLidarProfile(
        model_id="tim_4xx",
        display_name="SICK TiM4xx",
        launch_file="launch/sick_tim_4xx.launch",
        default_hostname="192.168.1.11",
        port_arg="port",
        default_port=2112,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1
    ),
    "tim_5xx": SickLidarProfile(
        model_id="tim_5xx",
        display_name="SICK TiM5xx",
        launch_file="launch/sick_tim_5xx.launch",
        default_hostname="192.168.1.11",
        port_arg="port",
        default_port=2112,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1
    ),
    "tim_7xx": SickLidarProfile(
        model_id="tim_7xx",
        display_name="SICK TiM7xx",
        launch_file="launch/sick_tim_7xx.launch",
        default_hostname="192.168.1.11",
        port_arg="port",
        default_port=2112,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1
    ),
    "lms_1xx": SickLidarProfile(
        model_id="lms_1xx",
        display_name="SICK LMS1xx",
        launch_file="launch/sick_lms_1xx.launch",
        default_hostname="192.168.1.14",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1
    ),
    "lms_5xx": SickLidarProfile(
        model_id="lms_5xx",
        display_name="SICK LMS5xx",
        launch_file="launch/sick_lms_5xx.launch",
        default_hostname="192.168.1.14",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1
    ),
    "lms_4xxx": SickLidarProfile(
        model_id="lms_4xxx",
        display_name="SICK LMS4xxx",
        launch_file="launch/sick_lms_4xxx.launch",
        default_hostname="192.168.1.14",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1
    ),
    "mrs_1xxx": SickLidarProfile(
        model_id="mrs_1xxx",
        display_name="SICK MRS1xxx",
        launch_file="launch/sick_mrs_1xxx.launch",
        default_hostname="192.168.1.41",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=4
    ),
    "mrs_6xxx": SickLidarProfile(
        model_id="mrs_6xxx",
        display_name="SICK MRS6xxx",
        launch_file="launch/sick_mrs_6xxx.launch",
        default_hostname="192.168.1.41",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=24
    ),
}


def get_all_profiles() -> List[SickLidarProfile]:
    """
    Returns all available LiDAR profiles in display order.
    
    Order: multiScan first, then TiM ascending, then LMS ascending, then MRS ascending.
    """
    # Define the desired order
    ordered_keys = [
        "multiscan",
        "tim_2xx", "tim_4xx", "tim_5xx", "tim_7xx",
        "lms_1xx", "lms_5xx", "lms_4xxx",
        "mrs_1xxx", "mrs_6xxx"
    ]
    
    return [_PROFILES[key] for key in ordered_keys]


def get_profile(model_id: str) -> SickLidarProfile:
    """
    Get a specific LiDAR profile by model ID.
    
    Args:
        model_id: The model identifier (e.g., "multiscan", "tim_5xx")
    
    Returns:
        SickLidarProfile for the requested model
    
    Raises:
        KeyError: If the model_id is not recognized
    """
    if model_id not in _PROFILES:
        valid_models = list(_PROFILES.keys())
        raise KeyError(f"Unknown lidar_type '{model_id}'. Valid options: {valid_models}")
    
    return _PROFILES[model_id]


def build_launch_args(
    model_id: str,
    hostname: str,
    port: Optional[int],
    udp_receiver_ip: Optional[str],
    imu_udp_port: Optional[int],
    add_transform_xyz_rpy: str
) -> str:
    """
    Build launch arguments string for a specific SICK LiDAR model.
    
    Args:
        model_id: The LiDAR model identifier
        hostname: IP address of the LiDAR device
        port: Port number (ignored for models without port_arg)
        udp_receiver_ip: UDP receiver IP (only for multiScan)
        imu_udp_port: IMU UDP port (only for multiScan)
        add_transform_xyz_rpy: Transform string in format "x,y,z,roll,pitch,yaw"
    
    Returns:
        Complete launch arguments string
    
    Raises:
        KeyError: If model_id is not recognized
    """
    profile = get_profile(model_id)
    
    # Base arguments
    args = f"{profile.launch_file} hostname:={hostname} add_transform_xyz_rpy:={add_transform_xyz_rpy}"
    
    # Add port argument if the model supports it and port is provided
    if profile.port_arg and port is not None:
        args += f" {profile.port_arg}:={port}"
    
    # Add UDP receiver IP for multiScan
    if profile.has_udp_receiver and udp_receiver_ip is not None:
        args += f" udp_receiver_ip:={udp_receiver_ip}"
    
    # Add IMU UDP port for multiScan
    if profile.has_imu_udp_port and imu_udp_port is not None:
        args += f" imu_udp_port:={imu_udp_port}"
    
    return args