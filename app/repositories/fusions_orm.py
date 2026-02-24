"""
ORM-based repository for fusion configurations using SQLAlchemy.
"""
import json
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.db.models import FusionModel
from app.db.session import SessionLocal


class FusionORMRepository:
    """SQLAlchemy ORM-based repository for fusion configurations"""
    
    def __init__(self, session: Optional[Session] = None):
        self._session = session
    
    def _get_session(self) -> Session:
        """Get database session (use provided or create new)"""
        if self._session is not None:
            return self._session

        # Ensure SessionLocal is bound (app startup does this; tests may not).
        from app.db.session import get_engine

        get_engine()
        return SessionLocal()
    
    def _should_close(self) -> bool:
        """Check if we should close the session (only if we created it)"""
        return self._session is None
    
    def list(self) -> List[Dict[str, Any]]:
        """List all fusion configurations"""
        session = self._get_session()
        try:
            fusions = session.query(FusionModel).all()
            return [fusion.to_dict() for fusion in fusions]
        finally:
            if self._should_close():
                session.close()
    
    def get_by_id(self, fusion_id: str) -> Optional[Dict[str, Any]]:
        """Get a fusion by ID"""
        session = self._get_session()
        try:
            fusion = session.query(FusionModel).filter(FusionModel.id == fusion_id).first()
            return fusion.to_dict() if fusion else None
        finally:
            if self._should_close():
                session.close()
    
    def upsert(self, config: Dict[str, Any]) -> str:
        """Create or update a fusion configuration"""
        session = self._get_session()
        try:
            record_id = config.get("id") or uuid.uuid4().hex
            sensor_ids_str = json.dumps(config.get("sensor_ids", []))
            
            # Check if record exists
            existing = session.query(FusionModel).filter(FusionModel.id == record_id).first()
            
            # Handle enabled flag
            enabled = config.get("enabled")
            if enabled is None and existing:
                enabled = existing.enabled
            if enabled is None:
                enabled = True
            
            if existing:
                # Update existing
                existing.name = config.get("name", existing.name)
                existing.topic = config.get("topic", existing.topic)
                existing._sensor_ids = sensor_ids_str
                existing.pipeline_name = config.get("pipeline_name", existing.pipeline_name)
                existing.enabled = enabled
            else:
                # Create new
                fusion = FusionModel(
                    id=record_id,
                    name=config.get("name"),
                    topic=config.get("topic"),
                    _sensor_ids=sensor_ids_str,
                    pipeline_name=config.get("pipeline_name"),
                    enabled=enabled
                )
                session.add(fusion)
            
            session.commit()
            return record_id
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()
    
    def set_enabled(self, fusion_id: str, enabled: bool) -> None:
        """Enable or disable a fusion"""
        session = self._get_session()
        try:
            fusion = session.query(FusionModel).filter(FusionModel.id == fusion_id).first()
            if fusion:
                fusion.enabled = enabled
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()
    
    def delete(self, fusion_id: str) -> None:
        """Delete a fusion configuration"""
        session = self._get_session()
        try:
            fusion = session.query(FusionModel).filter(FusionModel.id == fusion_id).first()
            if fusion:
                session.delete(fusion)
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()
