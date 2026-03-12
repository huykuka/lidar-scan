"""Node-related schema models for DAG processing nodes."""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, ConfigDict


class NodeRecord(BaseModel):
    """Full node configuration record from database."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                     "name": "MultiScan Left",
                     "type": "sensor",
                     "category": "sensor",
                     "enabled": True,
                     "visible": True,
                     "config": {
                        "lidar_type": "multiscan",
                        "hostname": "192.168.1.10",
                        "udp_receiver_ip": "192.168.1.100",
                        "port": 2115
                    },
                    "x": 120.0,
                    "y": 200.0
                },
                {
                    "id": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
                    "name": "Point Cloud Fusion",
                    "type": "fusion",
                     "category": "fusion", 
                     "enabled": True,
                     "visible": True,
                     "config": {
                        "fusion_method": "icp_registration",
                        "distance_threshold": 0.05,
                        "max_iterations": 100
                    },
                    "x": 300.0,
                    "y": 200.0
                }
            ]
        }
    )
    
    id: str
    name: str
    type: str
    category: str
    enabled: bool
    visible: bool = True
    config: Dict[str, Any] = {}
    x: Optional[float] = None
    y: Optional[float] = None


class NodeStatusItem(BaseModel):
    """Runtime status information for a single node."""
    id: str
    name: str
    type: str
    category: str
    enabled: bool
    visible: bool = True
    running: bool
    topic: Optional[str] = None  # null when visible=false
    last_frame_at: Optional[float] = None
    frame_age_seconds: Optional[float] = None
    last_error: Optional[str] = None
    throttle_ms: float = 0.0
    throttled_count: int = 0


class NodesStatusResponse(BaseModel):
    """Response containing status information for all nodes."""
    nodes: List[NodeStatusItem]