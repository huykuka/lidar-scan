"""Node-related schema models for DAG processing nodes."""

from typing import Dict, Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.pose import Pose


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
    pose: Optional[Pose] = None
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


# ---------------------------------------------------------------------------
# Reload schemas (node-reload-improvement feature)
# ---------------------------------------------------------------------------

class SelectiveReloadResult(BaseModel):
    """Internal result model returned by SelectiveReloadManager.reload_single_node().

    Not exposed via REST directly — used as the service-layer return type.
    Spec: .opencode/plans/node-reload-improvement/api-spec.md § 5
    """
    node_id: str = Field(..., description="ID of the reloaded node.")
    status: Literal["reloaded", "error"] = Field(..., description="Outcome of the reload attempt.")
    duration_ms: float = Field(..., description="Wall-clock duration of the reload in milliseconds.")
    ws_topic: Optional[str] = Field(None, description="WebSocket topic that was preserved (None if no WS topic).")
    error_message: Optional[str] = Field(None, description="Error description when status='error'.")
    rolled_back: bool = Field(False, description="True if the old instance was restored after a failed reload.")


class NodeReloadResponse(BaseModel):
    """REST response for POST /api/v1/nodes/{node_id}/reload.

    Spec: .opencode/plans/node-reload-improvement/api-spec.md § 2
    """
    node_id: str = Field(..., description="ID of the reloaded node.")
    status: Literal["reloaded"] = Field(..., description="Always 'reloaded' on HTTP 200.")
    duration_ms: float = Field(..., description="Actual reload duration in milliseconds.")
    ws_topic: Optional[str] = Field(None, description="The WebSocket topic that was preserved.")


class ReloadStatusResponse(BaseModel):
    """REST response for GET /api/v1/nodes/reload/status.

    Spec: .opencode/plans/node-reload-improvement/api-spec.md § 3
    """
    locked: bool = Field(..., description="True if _reload_lock is currently held.")
    reload_in_progress: bool = Field(..., description="Alias for locked (convenience).")
    active_reload_node_id: Optional[str] = Field(
        None,
        description="Node currently being selectively reloaded. None for full reload or when idle.",
    )
    estimated_completion_ms: Optional[int] = Field(
        None,
        description="Static time estimate: 150ms for selective, 3000ms for full. None when idle.",
    )