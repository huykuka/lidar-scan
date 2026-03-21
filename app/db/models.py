"""SQLAlchemy ORM models.

Engine/session initialization lives in `app.db.session`.
"""

from __future__ import annotations

from typing import cast, Optional


from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import datetime
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
        pose = config.pop("pose", None)   # surface pose at top level; local mutation only
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
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

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
    quality: Mapped[str] = mapped_column(String, nullable=False)  # "excellent", "good", "poor"
    stages_used_json: Mapped[str] = mapped_column(String, nullable=False)  # JSON array: ["global", "icp"]
    pose_before_json: Mapped[str] = mapped_column(String, nullable=False)  # JSON dict: {x, y, z, roll, pitch, yaw}
    pose_after_json: Mapped[str] = mapped_column(String, nullable=False)   # JSON dict: {x, y, z, roll, pitch, yaw}
    transformation_matrix_json: Mapped[str] = mapped_column(String, nullable=False)  # JSON 4x4 matrix
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(String, default="")
    
    # NEW: Provenance tracking fields for ICP Flow Alignment
    source_sensor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    processing_chain_json: Mapped[str] = mapped_column(String, default="[]")
    run_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

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
