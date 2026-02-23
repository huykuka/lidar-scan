"""Repository for recording persistence using SQLAlchemy ORM."""
from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy.orm import Session

from app.db.models import RecordingModel


class RecordingsRepository:
    """Repository for managing recording configurations."""

    def __init__(self, db: Session):
        self.db = db

    def list(self, topic: str | None = None) -> list[dict]:
        """
        List all recordings, optionally filtered by topic.

        Args:
            topic: Optional topic filter

        Returns:
            List of recording dictionaries
        """
        query = self.db.query(RecordingModel)
        
        if topic:
            query = query.filter(RecordingModel.topic == topic)
        
        recordings = query.order_by(RecordingModel.created_at.desc()).all()
        return [r.to_dict() for r in recordings]

    def get_by_id(self, recording_id: str) -> dict | None:
        """
        Get a recording by ID.

        Args:
            recording_id: Recording ID

        Returns:
            Recording dictionary or None if not found
        """
        recording = self.db.query(RecordingModel).filter(RecordingModel.id == recording_id).first()
        return recording.to_dict() if recording else None

    def create(self, recording_data: dict) -> dict:
        """
        Create a new recording.

        Args:
            recording_data: Recording data dictionary

        Returns:
            Created recording dictionary
        """
        import json
        
        # Ensure created_at is set
        if "created_at" not in recording_data:
            recording_data["created_at"] = datetime.utcnow().isoformat()
        
        # Convert metadata dict to JSON string if needed
        if "metadata" in recording_data and isinstance(recording_data["metadata"], dict):
            recording_data["metadata_json"] = json.dumps(recording_data["metadata"])
            del recording_data["metadata"]
        
        recording = RecordingModel(**recording_data)
        self.db.add(recording)
        self.db.commit()
        self.db.refresh(recording)
        
        return recording.to_dict()

    def delete(self, recording_id: str) -> bool:
        """
        Delete a recording.

        Args:
            recording_id: Recording ID

        Returns:
            True if deleted, False if not found
        """
        recording = self.db.query(RecordingModel).filter(RecordingModel.id == recording_id).first()
        
        if not recording:
            return False
        
        self.db.delete(recording)
        self.db.commit()
        
        return True

    def update(self, recording_id: str, updates: dict) -> dict | None:
        """
        Update a recording.

        Args:
            recording_id: Recording ID
            updates: Dictionary of fields to update

        Returns:
            Updated recording dictionary or None if not found
        """
        import json
        
        recording = self.db.query(RecordingModel).filter(RecordingModel.id == recording_id).first()
        
        if not recording:
            return None
        
        # Convert metadata dict to JSON string if needed
        if "metadata" in updates and isinstance(updates["metadata"], dict):
            updates["metadata_json"] = json.dumps(updates["metadata"])
            del updates["metadata"]
        
        for key, value in updates.items():
            if hasattr(recording, key):
                setattr(recording, key, value)
        
        self.db.commit()
        self.db.refresh(recording)
        
        return recording.to_dict()

    def get_by_sensor_id(self, sensor_id: str) -> list[dict]:
        """
        Get all recordings for a specific sensor.

        Args:
            sensor_id: Sensor ID

        Returns:
            List of recording dictionaries
        """
        recordings = (
            self.db.query(RecordingModel)
            .filter(RecordingModel.sensor_id == sensor_id)
            .order_by(RecordingModel.created_at.desc())
            .all()
        )
        return [r.to_dict() for r in recordings]
