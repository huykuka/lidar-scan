"""Replay DTOs."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CreateReplayRequest(BaseModel):
    """Start an offline replay of a recording through the sub-graph of a Playback node."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "recording_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                "playback_node_id": "0f9e8d7c6b5a43210f9e8d7c6b5a4321",
                "label": "baseline",
                "overrides": {"<node_id>": {"threshold": 0.15}},
            }]
        }
    )

    recording_id: str
    playback_node_id: str
    label: str = Field(default="", max_length=80)
    overrides: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-node config overrides merged over the saved DAG config for this run only.",
    )
    capture_nodes: Optional[List[str]] = Field(
        default=None,
        description=(
            "Nodes whose point clouds are stored for visual diff. Omit to capture the final "
            "nodes of the replayed sub-graph and the nodes feeding them; send [] to capture nothing."
        ),
    )


class CreateSweepRequest(BaseModel):
    """Run the same recording once per value of one node parameter."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "recording_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                "playback_node_id": "0f9e8d7c6b5a43210f9e8d7c6b5a4321",
                "node_id": "df145a39f8a74e939ee11f6f325c1df8",
                "parameter": "radius",
                "values": [0.3, 0.5, 0.7, 1.0, 1.5],
            }]
        }
    )

    recording_id: str
    playback_node_id: str
    node_id: str
    parameter: str
    values: List[Any] = Field(min_length=1, max_length=30)
    label: str = Field(default="", max_length=80)
    capture_nodes: Optional[List[str]] = None
    include_current: bool = Field(
        default=True,
        description="Also run the pipeline's current value of the parameter as a baseline.",
    )


class SweepResponse(BaseModel):
    id: str
    label: str
    recording_id: str
    playback_node_id: str
    node_id: str
    parameter: str
    values: List[Any]
    created_at: str
    progress: Optional[Dict[str, int]] = None


class ListSweepsResponse(BaseModel):
    sweeps: List[SweepResponse]
    total: int


class CreateTargetRequest(BaseModel):
    """Ground truth: the value a metric should have for a recording."""
    recording_id: str
    node_id: str
    metric_key: str = Field(min_length=1)
    expected: float
    tolerance: Optional[float] = Field(default=None, ge=0)
    label: str = Field(default="", max_length=80)


class TargetResponse(BaseModel):
    id: str
    recording_id: str
    node_id: str
    metric_key: str
    label: str
    expected: float
    tolerance: Optional[float] = None
    created_at: str


class ListTargetsResponse(BaseModel):
    targets: List[TargetResponse]


class ReplayRunResponse(BaseModel):
    id: str
    label: str
    recording_id: str
    playback_node_id: str
    status: str
    frames_total: int
    frames_processed: int
    config_hash: str
    overrides: Dict[str, Any]
    summary: Dict[str, Any]
    error: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    sweep_id: Optional[str] = None
    capture_nodes: Optional[List[str]] = None
    scores: Optional[Dict[str, Any]] = None
    #: Sweep runs only: the value of the swept parameter this run used.
    x_value: Optional[Any] = None
    #: Sweep runs only: True for the run that uses the pipeline's current value.
    is_baseline: Optional[bool] = None
    config_snapshot: Optional[Dict[str, Any]] = None


class SweepDetailResponse(BaseModel):
    sweep: SweepResponse
    runs: List[ReplayRunResponse]
    targets: List[TargetResponse]
    #: Run closest to the ground truth (only when targets exist and runs completed).
    best_run_id: Optional[str] = None


class ApplyResponse(BaseModel):
    applied: List[Dict[str, Any]]
    config_version: int
    reload_mode: str
    reloaded_node_ids: List[str]


class ListReplayRunsResponse(BaseModel):
    runs: List[ReplayRunResponse]
    total: int
