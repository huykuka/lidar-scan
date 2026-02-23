"""SQLAlchemy ORM models.

Engine/session initialization lives in `app.db.session`.
"""

from __future__ import annotations

from typing import cast


from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LidarModel(Base):
    """SQLAlchemy model for lidars table."""

    __tablename__ = "lidars"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    topic_prefix: Mapped[str | None] = mapped_column(String)
    launch_args: Mapped[str] = mapped_column(String, nullable=False)
    pipeline_name: Mapped[str | None] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String, default="real")
    pcd_path: Mapped[str | None] = mapped_column(String)
    x: Mapped[float] = mapped_column(Float, default=0.0)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    z: Mapped[float] = mapped_column(Float, default=0.0)
    roll: Mapped[float] = mapped_column(Float, default=0.0)
    pitch: Mapped[float] = mapped_column(Float, default=0.0)
    yaw: Mapped[float] = mapped_column(Float, default=0.0)
    imu_udp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "topic_prefix": self.topic_prefix,
            "launch_args": self.launch_args,
            "pipeline_name": self.pipeline_name,
            "mode": self.mode,
            "pcd_path": self.pcd_path,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "roll": self.roll,
            "pitch": self.pitch,
            "yaw": self.yaw,
            "imu_udp_port": self.imu_udp_port,
            "enabled": self.enabled,
        }


class RecordingModel(Base):
    """SQLAlchemy model for recordings table."""

    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    sensor_id: Mapped[str | None] = mapped_column(String)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    recording_timestamp: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[str] = mapped_column(String, nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    def to_dict(self) -> dict:
        import json

        return {
            "id": self.id,
            "name": self.name,
            "topic": self.topic,
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


class FusionModel(Base):
    """SQLAlchemy model for fusions table."""

    __tablename__ = "fusions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    _sensor_ids: Mapped[str] = mapped_column("sensor_ids", String, nullable=False)  # JSON array string
    pipeline_name: Mapped[str | None] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    def to_dict(self) -> dict:
        import json

        sensor_ids = cast(str, self._sensor_ids)

        return {
            "id": self.id,
            "name": self.name,
            "topic": self.topic,
            "sensor_ids": json.loads(sensor_ids) if sensor_ids else [],
            "pipeline_name": self.pipeline_name,
            "enabled": self.enabled,
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
