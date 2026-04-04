"""Pydantic schemas for DAG config save/load endpoints."""

from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.edges import EdgeRecord
from app.api.v1.schemas.nodes import NodeRecord


class DagConfigResponse(BaseModel):
    """Response schema for GET /api/v1/dag/config."""

    config_version: int
    nodes: List[NodeRecord]
    edges: List[EdgeRecord]


class DagConfigSaveRequest(BaseModel):
    """Request body for PUT /api/v1/dag/config."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "base_version": 7,
                "nodes": [
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
                            "port": 2115,
                        },
                        "pose": None,
                        "x": 120.0,
                        "y": 200.0,
                    },
                    {
                        "id": "__new__1",
                        "name": "Debug Pass-Through",
                        "type": "debug_save",
                        "category": "operation",
                        "enabled": True,
                        "visible": False,
                        "config": {"op_type": "debug_save"},
                        "pose": None,
                        "x": 350.0,
                        "y": 300.0,
                    },
                ],
                "edges": [
                    {
                        "id": "edge001",
                        "source_node": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                        "source_port": "out",
                        "target_node": "__new__1",
                        "target_port": "in",
                    }
                ],
            }
        }
    )

    base_version: int
    nodes: List[NodeRecord]
    edges: List[EdgeRecord]


class DagConfigSaveResponse(BaseModel):
    """Response schema for PUT /api/v1/dag/config."""

    config_version: int
    node_id_map: Dict[str, str]
    reload_mode: Literal["selective", "full", "none"] = Field(
        "full",
        description=(
            "Which reload path was taken: "
            "'selective' = only param-changed nodes reloaded, "
            "'full' = entire DAG reloaded (topology change), "
            "'none' = no runtime reload needed (cosmetic changes only)."
        ),
    )
    reloaded_node_ids: List[str] = Field(
        default_factory=list,
        description="IDs of nodes that were selectively reloaded. Empty when reload_mode != 'selective'.",
    )
