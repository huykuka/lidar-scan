"""
Standardized node status Pydantic schemas.

Spec: .opencode/plans/node-status-standardization/api-spec.md § 1.1

This module defines the contract for node status reporting across all DAG nodes.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class OperationalState(str, Enum):
    """Lifecycle state of the node process / worker.

    INITIALIZE  – Node is starting up (worker spawning, sensor handshake)
    RUNNING     – Node is actively processing data
    STOPPED     – Node is intentionally stopped or disabled
    ERROR       – Node encountered a fatal / non-recoverable error
    """
    INITIALIZE = "INITIALIZE"
    RUNNING    = "RUNNING"
    STOPPED    = "STOPPED"
    ERROR      = "ERROR"


class ApplicationState(BaseModel):
    """Node-specific runtime state. JSON-serializable only.

    Examples
    --------
    Sensor:      ApplicationState(label="connection_status", value="connected", color="green")
    Calibration: ApplicationState(label="calibrating",       value=True,        color="blue")
    IfCondition: ApplicationState(label="condition",         value="true",      color="green")
    Fusion:      ApplicationState(label="fusing",            value=3,           color="blue")
    """
    label: str           = Field(..., description="Human-readable state identifier")
    value: Any           = Field(..., description="JSON-serializable value (str, bool, int, float)")
    color: Optional[str] = Field(None, description="UI hint: green | blue | orange | red | gray")


class NodeStatusUpdate(BaseModel):
    """Standardised status update for one DAG node.

    This is emitted by ``ModuleNode.emit_status()`` and collected by
    ``StatusAggregator`` before being broadcast on the system_status topic.
    """
    node_id:           str                     = Field(..., description="Unique node identifier")
    operational_state: OperationalState        = Field(..., description="Node lifecycle state")
    application_state: Optional[ApplicationState] = Field(None, description="Node-specific state")
    error_message:     Optional[str]           = Field(None, description="Only set when operational_state=ERROR")
    timestamp:         float                   = Field(default_factory=time.time, description="Unix epoch seconds")

    model_config = {"use_enum_values": True}


class SystemStatusBroadcast(BaseModel):
    """WebSocket payload broadcast on the system_status topic."""
    nodes: list[NodeStatusUpdate] = Field(..., description="All registered node statuses")
