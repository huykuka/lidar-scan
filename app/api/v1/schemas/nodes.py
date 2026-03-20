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
    """Runtime status information for a single node.

    The core fields (node_id, operational_state, application_state,
    error_message, timestamp) mirror NodeStatusUpdate from the status schema
    spec.  Additional DB-metadata fields (name, type, category, enabled,
    visible, topic, throttle_*) are augmented by the REST endpoint.
    """
    node_id: str
    operational_state: str
    application_state: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    timestamp: Optional[float] = None
    # DB metadata augmented by the REST endpoint
    name: str
    type: str
    category: str
    enabled: bool
    visible: bool = True
    topic: Optional[str] = None  # null when visible=false
    throttle_ms: float = 0.0
    throttled_count: int = 0


class NodesStatusResponse(BaseModel):
    """Response containing status information for all nodes."""
    nodes: List[NodeStatusItem]