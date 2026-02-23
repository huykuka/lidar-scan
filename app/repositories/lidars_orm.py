"""
ORM-based repository for lidar configurations using SQLAlchemy.
"""
import json
import uuid
import re
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.db.models import LidarModel
from app.db.session import SessionLocal


class LidarORMRepository:
    """SQLAlchemy ORM-based repository for lidar configurations"""
    
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
        """List all lidar configurations"""
        session = self._get_session()
        try:
            lidars = session.query(LidarModel).all()
            return [lidar.to_dict() for lidar in lidars]
        finally:
            if self._should_close():
                session.close()
    
    def get_by_id(self, lidar_id: str) -> Optional[Dict[str, Any]]:
        """Get a lidar by ID"""
        session = self._get_session()
        try:
            lidar = session.query(LidarModel).filter(LidarModel.id == lidar_id).first()
            return lidar.to_dict() if lidar else None
        finally:
            if self._should_close():
                session.close()
    
    def _slugify(self, val: str) -> str:
        """Convert string to URL-friendly format"""
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", (val or "").strip())
        base = re.sub(r"_+", "_", base).strip("_-")
        return base or "sensor"
    
    def _generate_topic_prefix(self, session: Session, config: Dict[str, Any], record_id: str) -> str:
        """Generate unique topic_prefix"""
        topic_prefix = config.get("topic_prefix")
        
        # If topic_prefix not provided, check if record exists
        if topic_prefix is None:
            existing = session.query(LidarModel).filter(LidarModel.id == record_id).first()
            if existing and existing.topic_prefix:
                topic_prefix = existing.topic_prefix
        
        # Generate from name if still None
        if topic_prefix is None:
            desired = config.get("name") or record_id
            requested = self._slugify(desired)
        else:
            requested = self._slugify(topic_prefix)
        
        # Check for collisions
        in_use = {
            lidar.topic_prefix
            for lidar in session.query(LidarModel)
                .filter(LidarModel.id != record_id)
                .filter(LidarModel.topic_prefix.isnot(None))
                .all()
        }
        
        if requested not in in_use:
            return requested
        
        # Handle collision
        suffix = self._slugify(record_id)[:8]
        candidate = f"{requested}_{suffix}" if suffix else f"{requested}_1"
        i = 2
        while candidate in in_use:
            candidate = f"{requested}_{suffix}_{i}" if suffix else f"{requested}_{i}"
            i += 1
        
        return candidate
    
    def upsert(self, config: Dict[str, Any]) -> str:
        """Create or update a lidar configuration"""
        session = self._get_session()
        try:
            record_id = config.get("id") or uuid.uuid4().hex
            
            # Generate topic_prefix
            topic_prefix = self._generate_topic_prefix(session, config, record_id)
            
            # Check if record exists
            existing = session.query(LidarModel).filter(LidarModel.id == record_id).first()
            
            # Handle enabled flag
            enabled = config.get("enabled")
            if enabled is None and existing:
                enabled = existing.enabled
            if enabled is None:
                enabled = True
            
            if existing:
                # Update existing
                existing.name = config.get("name", existing.name)
                existing.topic_prefix = topic_prefix
                existing.launch_args = config.get("launch_args", existing.launch_args)
                existing.pipeline_name = config.get("pipeline_name", existing.pipeline_name)
                existing.mode = config.get("mode", existing.mode)
                existing.pcd_path = config.get("pcd_path", existing.pcd_path)
                existing.x = config.get("x", existing.x)
                existing.y = config.get("y", existing.y)
                existing.z = config.get("z", existing.z)
                existing.roll = config.get("roll", existing.roll)
                existing.pitch = config.get("pitch", existing.pitch)
                existing.yaw = config.get("yaw", existing.yaw)
                existing.imu_udp_port = config.get("imu_udp_port", existing.imu_udp_port)
                existing.enabled = enabled
            else:
                # Create new
                lidar = LidarModel(
                    id=record_id,
                    name=config.get("name"),
                    topic_prefix=topic_prefix,
                    launch_args=config.get("launch_args"),
                    pipeline_name=config.get("pipeline_name"),
                    mode=config.get("mode", "real"),
                    pcd_path=config.get("pcd_path"),
                    x=config.get("x", 0.0),
                    y=config.get("y", 0.0),
                    z=config.get("z", 0.0),
                    roll=config.get("roll", 0.0),
                    pitch=config.get("pitch", 0.0),
                    yaw=config.get("yaw", 0.0),
                    imu_udp_port=config.get("imu_udp_port"),
                    enabled=enabled,
                )
                session.add(lidar)
            
            session.commit()
            return record_id
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()
    
    def set_enabled(self, lidar_id: str, enabled: bool) -> None:
        """Enable or disable a lidar"""
        session = self._get_session()
        try:
            lidar = session.query(LidarModel).filter(LidarModel.id == lidar_id).first()
            if lidar:
                lidar.enabled = enabled
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()
    
    def delete(self, lidar_id: str) -> None:
        """Delete a lidar configuration"""
        session = self._get_session()
        try:
            lidar = session.query(LidarModel).filter(LidarModel.id == lidar_id).first()
            if lidar:
                session.delete(lidar)
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()
