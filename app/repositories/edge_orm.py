"""
Repository for edge persistence using SQLAlchemy ORM.
"""
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.db.models import EdgeModel
from app.db.session import SessionLocal


class EdgeRepository:
    """SQLAlchemy ORM-based repository for edges"""
    
    def __init__(self, session: Optional[Session] = None):
        self._session = session
    
    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        from app.db.session import get_engine
        get_engine()
        return SessionLocal()
    
    def _should_close(self) -> bool:
        return self._session is None
    
    def list(self) -> List[Dict[str, Any]]:
        """Get all edges from database"""
        session = self._get_session()
        try:
            edges = session.query(EdgeModel).all()
            return [edge.to_dict() for edge in edges]
        finally:
            if self._should_close():
                session.close()
                
    def save_all(self, edges_data: List[Dict[str, Any]]) -> None:
        """Replace all current edges with the new set (since edges are tightly controlled by the canvas)"""
        session = self._get_session()
        try:
            session.query(EdgeModel).delete()
            for edata in edges_data:
                edge = EdgeModel(
                    id=edata.get("id") or uuid.uuid4().hex,
                    source_node=edata["source_node"],
                    source_port=edata["source_port"],
                    target_node=edata["target_node"],
                    target_port=edata["target_port"]
                )
                session.add(edge)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()
