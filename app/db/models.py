"""SQLAlchemy ORM models.

Engine/session initialization lives in `app.db.session`.
"""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class NodeModel(Base):
    """SQLAlchemy model for nodes table."""

    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Store all configurations (like topic_prefix, xyz, args) in a JSON string
    config_json: Mapped[str] = mapped_column("config", String, default="{}")
    # Canvas position
    x: Mapped[float] = mapped_column(Float, default=100.0)
    y: Mapped[float] = mapped_column(Float, default=100.0)

    def to_dict(self) -> dict:
        import json

        config = json.loads(self.config_json) if self.config_json else {}
        pose = config.pop(
            "pose", None
        )  # surface pose at top level; local mutation only
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "category": self.category,
            "enabled": self.enabled,
            "visible": self.visible,
            "config": config,
            "pose": pose,
            "x": self.x,
            "y": self.y,
        }


class EdgeModel(Base):
    """SQLAlchemy model for edges table."""

    __tablename__ = "edges"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_node: Mapped[str] = mapped_column(String, nullable=False)
    source_port: Mapped[str] = mapped_column(String, nullable=False)
    target_node: Mapped[str] = mapped_column(String, nullable=False)
    target_port: Mapped[str] = mapped_column(String, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_node": self.source_node,
            "source_port": self.source_port,
            "target_node": self.target_node,
            "target_port": self.target_port,
        }


class DagMetaModel(Base):
    """Single-row table holding the monotonic DAG config version counter."""

    __tablename__ = "dag_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    config_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class RecordingModel(Base):
    """SQLAlchemy model for recordings table."""

    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    node_id: Mapped[str] = mapped_column(String, nullable=False)
    sensor_id: Mapped[str | None] = mapped_column(String)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    recording_timestamp: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[str] = mapped_column(String, nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ready")
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )

    def to_dict(self) -> dict:
        import json

        return {
            "id": self.id,
            "name": self.name,
            "node_id": self.node_id,
            "sensor_id": self.sensor_id,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "frame_count": self.frame_count,
            "duration_seconds": self.duration_seconds,
            "recording_timestamp": self.recording_timestamp,
            "metadata": json.loads(self.metadata_json),
            "thumbnail_path": self.thumbnail_path,
            "status": self.status,
            "created_at": self.created_at,
        }


class CalibrationHistoryModel(Base):
    """SQLAlchemy model for calibration_history table."""

    __tablename__ = "calibration_history"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sensor_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    reference_sensor_id: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    fitness: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    quality: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "excellent", "good", "poor"
    stages_used_json: Mapped[str] = mapped_column(
        String, nullable=False
    )  # JSON array: ["global", "icp"]
    pose_before_json: Mapped[str] = mapped_column(
        String, nullable=False
    )  # JSON dict: {x, y, z, roll, pitch, yaw}
    pose_after_json: Mapped[str] = mapped_column(
        String, nullable=False
    )  # JSON dict: {x, y, z, roll, pitch, yaw}
    transformation_matrix_json: Mapped[str] = mapped_column(
        String, nullable=False
    )  # JSON 4x4 matrix
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(String, default="")

    # NEW: Provenance tracking fields for ICP Flow Alignment
    source_sensor_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )
    processing_chain_json: Mapped[str] = mapped_column(String, default="[]")
    run_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    node_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    accepted_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    accepted_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rollback_source_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    registration_method_json: Mapped[str] = mapped_column(String, default="null")

    def to_dict(self) -> dict:
        import json

        return {
            "id": self.id,
            "sensor_id": self.sensor_id,
            "reference_sensor_id": self.reference_sensor_id,
            "timestamp": self.timestamp,
            "fitness": self.fitness,
            "rmse": self.rmse,
            "quality": self.quality,
            "stages_used": json.loads(self.stages_used_json),
            "pose_before": json.loads(self.pose_before_json),
            "pose_after": json.loads(self.pose_after_json),
            "transformation_matrix": json.loads(self.transformation_matrix_json),
            "accepted": self.accepted,
            "notes": self.notes,
            "source_sensor_id": self.source_sensor_id,
            "processing_chain": json.loads(self.processing_chain_json or "[]"),
            "run_id": self.run_id,
            "node_id": self.node_id,
            "accepted_at": self.accepted_at,
            "accepted_by": self.accepted_by,
            "rollback_source_id": self.rollback_source_id,
            "registration_method": json.loads(self.registration_method_json or "null"),
        }


class ApplicationResultModel(Base):
    """SQLAlchemy model for application_results table.

    Stores results produced by application nodes (e.g. VolumeCalculation, VehicleProfiler).
    ``node_id`` is a logical reference to the DAG node — no FK enforced (DAG nodes are
    runtime objects, not DB entities).  Lifecycle integrity is enforced by the orchestrator
    delete hook (``delete_results_by_node``).
    """

    __tablename__ = "application_results"

    result_id: Mapped[str] = mapped_column(String, primary_key=True)
    node_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_json: Mapped[str] = mapped_column(
        "metadata", String, nullable=False, default="{}"
    )
    pcd_files_json: Mapped[str] = mapped_column(
        "pcd_files", String, nullable=False, default="[]"
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="success")

    __table_args__ = (Index("idx_results_node_ts", "node_id", "timestamp"),)

    def to_dict(self) -> dict:
        import json

        return {
            "result_id": self.result_id,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "metadata": json.loads(self.metadata_json) if self.metadata_json else {},
            "pcd_files": json.loads(self.pcd_files_json) if self.pcd_files_json else [],
            "status": self.status,
        }


class UserModel(Base):
    """User accounts for authentication and role-based access control."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="user")
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at,
        }


class NodeTypeRegistryModel(Base):
    """Tracks which node types are enabled/disabled in the palette.

    One row per node type (e.g. ``truck_bin_detection``).  The ``enabled``
    flag controls whether the definition appears in ``GET /nodes/definitions``
    and is available for use in the DAG canvas.
    """

    __tablename__ = "node_type_registry"

    type: Mapped[str] = mapped_column(String, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "enabled": self.enabled,
        }


class ReplayRunModel(Base):
    """SQLAlchemy model for replay_runs table.

    One offline replay of a recording through a snapshot of the DAG.  Per-frame
    outputs live in ``data/replays/<id>.json``; the row keeps config + summary.
    """

    __tablename__ = "replay_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False, default="")
    recording_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    playback_node_id: Mapped[str] = mapped_column(String, nullable=False)
    # queued | running | completed | failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    frames_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frames_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config_hash: Mapped[str] = mapped_column(String, nullable=False, default="")
    overrides_json: Mapped[str] = mapped_column("overrides", String, nullable=False, default="{}")
    config_snapshot_json: Mapped[str] = mapped_column(
        "config_snapshot", String, nullable=False, default="{}"
    )
    summary_json: Mapped[str] = mapped_column("summary", String, nullable=False, default="{}")
    error: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    finished_at: Mapped[str | None] = mapped_column(String)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    # Parameter sweep this run belongs to (None for stand-alone runs).
    sweep_id: Mapped[str | None] = mapped_column(String, index=True)
    # Nodes whose point clouds were stored; "null" = unknown (runs created before this existed).
    capture_nodes_json: Mapped[str] = mapped_column(
        "capture_nodes", String, nullable=False, default="null"
    )

    def to_dict(self, include_snapshot: bool = False) -> dict:
        import json

        data = {
            "sweep_id": self.sweep_id,
            "capture_nodes": json.loads(self.capture_nodes_json or "null"),
            "id": self.id,
            "label": self.label,
            "recording_id": self.recording_id,
            "playback_node_id": self.playback_node_id,
            "status": self.status,
            "frames_total": self.frames_total,
            "frames_processed": self.frames_processed,
            "config_hash": self.config_hash,
            "overrides": json.loads(self.overrides_json or "{}"),
            "summary": json.loads(self.summary_json or "{}"),
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
        }
        if include_snapshot:
            data["config_snapshot"] = json.loads(self.config_snapshot_json or "{}")
        return data


class ReplaySweepModel(Base):
    """A parameter sweep: one replay run per value of a single node parameter."""

    __tablename__ = "replay_sweeps"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False, default="")
    recording_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    playback_node_id: Mapped[str] = mapped_column(String, nullable=False)
    node_id: Mapped[str] = mapped_column(String, nullable=False)
    parameter: Mapped[str] = mapped_column(String, nullable=False)
    values_json: Mapped[str] = mapped_column("values", String, nullable=False, default="[]")
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )

    def to_dict(self) -> dict:
        import json

        return {
            "id": self.id,
            "label": self.label,
            "recording_id": self.recording_id,
            "playback_node_id": self.playback_node_id,
            "node_id": self.node_id,
            "parameter": self.parameter,
            "values": json.loads(self.values_json or "[]"),
            "created_at": self.created_at,
        }


class ReplayTargetModel(Base):
    """Ground truth for a recording: the value a metric is expected to have."""

    __tablename__ = "replay_targets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    recording_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String, nullable=False)
    metric_key: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False, default="")
    expected: Mapped[float] = mapped_column(Float, nullable=False)
    # Absolute tolerance (same unit as the metric); None = informational only.
    tolerance: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "recording_id": self.recording_id,
            "node_id": self.node_id,
            "metric_key": self.metric_key,
            "label": self.label,
            "expected": self.expected,
            "tolerance": self.tolerance,
            "created_at": self.created_at,
        }


def init_db() -> None:
    # Kept for backwards-compatibility; prefer `app.db.migrate.ensure_schema`.
    from app.db.session import get_engine

    Base.metadata.create_all(bind=get_engine())


def get_db():
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
