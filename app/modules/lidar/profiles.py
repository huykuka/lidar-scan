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
    has_udp_receiver: bool  # True for models requiring udp_receiver_ip
    has_imu_udp_port: bool  # True for models supporting IMU data
    scan_layers: int  # informational: 1 = 2D, >1 = multi-layer
    # Backend-controlled UI elements
    thumbnail_url: Optional[str] = None  # URL to device thumbnail image
    icon_name: Optional[str] = None  # Synergy UI icon name  
    icon_color: Optional[str] = None  # Hex color for icon (e.g., "#FF6B35")


# Registry of all supported SICK LiDAR models
# Based on official SICK scan_xd documentation
_PROFILES = {
    # --- multiScan Series (3D Multi-Layer) ---
    "multiscan": SickLidarProfile(
        model_id="multiscan",
        display_name="SICK multiScan100",
        launch_file="launch/sick_multiscan.launch",
        default_hostname="192.168.100.124",
        port_arg="udp_port",
        default_port=2115,
        has_udp_receiver=True,
        has_imu_udp_port=True,
        scan_layers=16,
        thumbnail_url="/api/v1/assets/lidar/multiscan.png",
        icon_name="device_hub",
        icon_color="#0066CC"
    ),
    
    # --- TiM Series (2D Time-of-Flight) ---
    "tim_240": SickLidarProfile(
        model_id="tim_240",
        display_name="SICK TiM240 (Prototype)",
        launch_file="launch/sick_tim_240.launch",
        default_hostname="192.168.1.11",
        port_arg="port",
        default_port=2112,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/tim240.png",
        icon_name="sensors",
        icon_color="#FF6B35"
    ),
    "tim_5xx": SickLidarProfile(
        model_id="tim_5xx",
        display_name="SICK TiM5xx Family",
        launch_file="launch/sick_tim_5xx.launch",
        default_hostname="192.168.1.11",
        port_arg="port",
        default_port=2112,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/tim5xx.png",
        icon_name="sensors",
        icon_color="#FF6B35"
    ),
    "tim_7xx": SickLidarProfile(
        model_id="tim_7xx",
        display_name="SICK TiM7xx Family (Non-Safety)",
        launch_file="launch/sick_tim_7xx.launch",
        default_hostname="192.168.1.11",
        port_arg="port",
        default_port=2112,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/tim7xx.png",
        icon_name="sensors",
        icon_color="#FF6B35"
    ),
    "tim_7xxs": SickLidarProfile(
        model_id="tim_7xxs",
        display_name="SICK TiM7xxS Family (Safety Device)",
        launch_file="launch/sick_tim_7xxS.launch",
        default_hostname="192.168.1.11",
        port_arg="port",
        default_port=2112,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/tim7xxs.png",
        icon_name="verified_user",
        icon_color="#FF4444"
    ),
    
    # --- LMS Series (2D Laser Measurement) ---
    "lms_1xx": SickLidarProfile(
        model_id="lms_1xx",
        display_name="SICK LMS1xx Family",
        launch_file="launch/sick_lms_1xx.launch",
        default_hostname="192.168.1.14",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/lms1xx.png",
        icon_name="track_changes",
        icon_color="#00AA44"
    ),
    "lms_1xxx": SickLidarProfile(
        model_id="lms_1xxx",
        display_name="SICK LMS1104 (Firmware 1.x)",
        launch_file="launch/sick_lms_1xxx.launch",
        default_hostname="192.168.1.14",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/lms1xxx.png",
        icon_name="track_changes",
        icon_color="#00AA44"
    ),
    "lms_1xxx_v2": SickLidarProfile(
        model_id="lms_1xxx_v2",
        display_name="SICK LMS1104 (Firmware 2.x)",
        launch_file="launch/sick_lms_1xxx_v2.launch",
        default_hostname="192.168.1.14",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/lms1xxx_v2.png",
        icon_name="track_changes",
        icon_color="#00AA44"
    ),
    "lms_5xx": SickLidarProfile(
        model_id="lms_5xx",
        display_name="SICK LMS5xx Family",
        launch_file="launch/sick_lms_5xx.launch",
        default_hostname="192.168.1.14",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/lms5xx.png",
        icon_name="track_changes",
        icon_color="#00AA44"
    ),
    "lms_4xxx": SickLidarProfile(
        model_id="lms_4xxx",
        display_name="SICK LMS4000 Family",
        launch_file="launch/sick_lms_4xxx.launch",
        default_hostname="192.168.1.14",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/lms4xxx.png",
        icon_name="track_changes",
        icon_color="#00AA44"
    ),
    
    # --- MRS Series (3D Multi-Layer) ---
    "mrs_1xxx": SickLidarProfile(
        model_id="mrs_1xxx",
        display_name="SICK MRS1104",
        launch_file="launch/sick_mrs_1xxx.launch",
        default_hostname="192.168.1.41",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=4,
        thumbnail_url="/api/v1/assets/lidar/mrs1xxx.png",
        icon_name="3d_rotation",
        icon_color="#9C27B0"
    ),
    "mrs_6xxx": SickLidarProfile(
        model_id="mrs_6xxx",
        display_name="SICK MRS6124",
        launch_file="launch/sick_mrs_6xxx.launch",
        default_hostname="192.168.1.41",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=24,
        thumbnail_url="/api/v1/assets/lidar/mrs6xxx.png",
        icon_name="360",
        icon_color="#8A2BE2"
    ),
    
    # --- LRS Series (3D Radar) ---
    "lrs_4xxx": SickLidarProfile(
        model_id="lrs_4xxx",
        display_name="SICK LRS4000",
        launch_file="launch/sick_lrs_4xxx.launch",
        default_hostname="192.168.1.100",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/lrs4xxx.png",
        icon_name="radar",
        icon_color="#FF9800"
    ),
    "lrs_36x0": SickLidarProfile(
        model_id="lrs_36x0",
        display_name="SICK LRS36x0",
        launch_file="launch/sick_lrs_36x0.launch",
        default_hostname="192.168.1.100",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/lrs36x0.png",
        icon_name="radar",
        icon_color="#FF9800"
    ),
    "lrs_36x0_upside_down": SickLidarProfile(
        model_id="lrs_36x0_upside_down",
        display_name="SICK LRS36x0 (Upside Down)",
        launch_file="launch/sick_lrs_36x0_upside_down.launch",
        default_hostname="192.168.1.100",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/lrs36x0.png",
        icon_name="flip",
        icon_color="#FF9800"
    ),
    "lrs_36x1": SickLidarProfile(
        model_id="lrs_36x1",
        display_name="SICK LRS36x1",
        launch_file="launch/sick_lrs_36x1.launch",
        default_hostname="192.168.1.100",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/lrs36x1.png",
        icon_name="radar",
        icon_color="#FF9800"
    ),
    "lrs_36x1_upside_down": SickLidarProfile(
        model_id="lrs_36x1_upside_down",
        display_name="SICK LRS36x1 (Upside Down)",
        launch_file="launch/sick_lrs_36x1_upside_down.launch",
        default_hostname="192.168.1.100",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/lrs36x1.png",
        icon_name="flip",
        icon_color="#FF9800"
    ),
    
    # --- LD-MRS Series (Legacy Multi-Layer) ---
    "ldmrs": SickLidarProfile(
        model_id="ldmrs",
        display_name="SICK LD-MRS Family",
        launch_file="launch/sick_ldmrs.launch",
        default_hostname="192.168.1.41",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=4,
        thumbnail_url="/api/v1/assets/lidar/ldmrs.png",
        icon_name="memory",
        icon_color="#795548"
    ),
    
    # --- OEM Series ---
    "oem_15xx": SickLidarProfile(
        model_id="oem_15xx",
        display_name="SICK LD-OEM15xx",
        launch_file="launch/sick_oem_15xx.launch",
        default_hostname="192.168.1.50",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/oem15xx.png",
        icon_name="precision_manufacturing",
        icon_color="#607D8B"
    ),
    
    # --- NAV Series (Navigation) ---
    "nav_2xx": SickLidarProfile(
        model_id="nav_2xx",
        display_name="SICK NAV210/NAV245",
        launch_file="launch/sick_nav_2xx.launch",
        default_hostname="192.168.1.2",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/nav2xx.png",
        icon_name="navigation",
        icon_color="#2196F3"
    ),
    "nav_31x": SickLidarProfile(
        model_id="nav_31x",
        display_name="SICK NAV310",
        launch_file="launch/sick_nav_31x.launch",
        default_hostname="192.168.1.2",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/nav31x.png",
        icon_name="navigation",
        icon_color="#2196F3"
    ),
    "nav_350": SickLidarProfile(
        model_id="nav_350",
        display_name="SICK NAV350",
        launch_file="launch/sick_nav_350.launch",
        default_hostname="192.168.1.2",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/nav350.png",
        icon_name="navigation",
        icon_color="#2196F3"
    ),
    
    # --- RMS Series (Radar Multi-Sensor) ---
    "rms_xxxx": SickLidarProfile(
        model_id="rms_xxxx",
        display_name="SICK RMS1009/RMS2000",
        launch_file="launch/sick_rms_xxxx.launch",
        default_hostname="192.168.1.60",
        port_arg="",
        default_port=0,
        has_udp_receiver=False,
        has_imu_udp_port=False,
        scan_layers=1,
        thumbnail_url="/api/v1/assets/lidar/rms.png",
        icon_name="settings_input_antenna",
        icon_color="#E91E63"
    ),
    
    # --- picoScan Series (Compact 3D) ---
    "picoscan_120": SickLidarProfile(
        model_id="picoscan_120",
        display_name="SICK picoScan120",
        launch_file="launch/sick_picoscan_120.launch",
        default_hostname="192.168.1.70",
        port_arg="",
        default_port=0,
        has_udp_receiver=True,  # Requires UDP receiver like multiScan
        has_imu_udp_port=False,
        scan_layers=3,
        thumbnail_url="/api/v1/assets/lidar/picoscan120.png",
        icon_name="settings_overscan",
        icon_color="#4CAF50"
    ),
    "picoscan_150": SickLidarProfile(
        model_id="picoscan_150",
        display_name="SICK picoScan150",
        launch_file="launch/sick_picoscan.launch",
        default_hostname="192.168.1.70",
        port_arg="",
        default_port=0,
        has_udp_receiver=True,  # Requires UDP receiver like multiScan
        has_imu_udp_port=False,
        scan_layers=3,
        thumbnail_url="/api/v1/assets/lidar/picoscan150.png",
        icon_name="settings_overscan",
        icon_color="#4CAF50"
    ),
}


def get_all_profiles() -> List[SickLidarProfile]:
    """
    Returns all available LiDAR profiles in display order.
    
    Order: multiScan first, then TiM series, LMS series, MRS series,
    LRS series, legacy/specialty models, NAV series, RMS, and picoScan.
    """
    # Define the desired display order
    ordered_keys = [
        # Multi-layer 3D sensors first
        "multiscan",
        
        # TiM series (2D Time-of-Flight)
        "tim_240", "tim_5xx", "tim_7xx", "tim_7xxs",
        
        # LMS series (2D Laser Measurement)
        "lms_1xx", "lms_1xxx", "lms_1xxx_v2", "lms_5xx", "lms_4xxx",
        
        # MRS series (3D Multi-Layer)
        "mrs_1xxx", "mrs_6xxx",
        
        # LRS series (3D Radar)
        "lrs_4xxx", "lrs_36x0", "lrs_36x0_upside_down", "lrs_36x1", "lrs_36x1_upside_down",
        
        # Legacy and specialty
        "ldmrs", "oem_15xx",
        
        # Navigation series
        "nav_2xx", "nav_31x", "nav_350",
        
        # Radar multi-sensor
        "rms_xxxx",
        
        # picoScan series (compact 3D)
        "picoscan_120", "picoscan_150",
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
        udp_receiver_ip: UDP receiver IP (for multiScan and picoScan series)
        imu_udp_port: IMU UDP port (only for multiScan)
    
    Returns:
        Complete launch arguments string
    
    Raises:
        KeyError: If model_id is not recognized
    """
    profile = get_profile(model_id)
    
    # Base arguments
    args = f"{profile.launch_file} hostname:={hostname}"
    
    # Add port argument if the model supports it and port is provided
    if profile.port_arg and port is not None:
        args += f" {profile.port_arg}:={port}"
    
    # Add UDP receiver IP for models that require it (multiScan, picoScan)
    if profile.has_udp_receiver and udp_receiver_ip is not None:
        args += f" udp_receiver_ip:={udp_receiver_ip}"
    
    # Add IMU UDP port for multiScan only
    if profile.has_imu_udp_port and imu_udp_port is not None:
        args += f" imu_udp_port:={imu_udp_port}"
    
    return args