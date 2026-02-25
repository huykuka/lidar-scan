"""
ORM-based repository for nodes and edges using SQLAlchemy.
"""
import json
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.db.models import NodeModel, EdgeModel
from app.db.session import SessionLocal

class NodeRepository:
    """SQLAlchemy ORM-based repository for nodes"""
    
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
        session = self._get_session()
        try:
            nodes = session.query(NodeModel).all()
            return [node.to_dict() for node in nodes]
        finally:
            if self._should_close():
                session.close()
    
    def get_by_id(self, node_id: str) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            node = session.query(NodeModel).filter(NodeModel.id == node_id).first()
            return node.to_dict() if node else None
        finally:
            if self._should_close():
                session.close()
                
    def upsert(self, data: Dict[str, Any]) -> str:
        session = self._get_session()
        try:
            record_id = data.get("id") or uuid.uuid4().hex
            config_str = json.dumps(data.get("config", {}))
            enabled = data.get("enabled", True)
            
            existing = session.query(NodeModel).filter(NodeModel.id == record_id).first()
            if existing:
                existing.name = data.get("name", existing.name)
                existing.type = data.get("type", existing.type)
                existing.category = data.get("category", existing.category)
                existing.enabled = data.get("enabled", existing.enabled)
                if "config" in data:
                    existing.config_json = config_str
            else:
                node = NodeModel(
                    id=record_id,
                    name=data.get("name", ""),
                    type=data.get("type", ""),
                    category=data.get("category", ""),
                    enabled=enabled,
                    config_json=config_str
                )
                session.add(node)
                
            session.commit()
            return record_id
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()

    def set_enabled(self, node_id: str, enabled: bool) -> None:
        session = self._get_session()
        try:
            node = session.query(NodeModel).filter(NodeModel.id == node_id).first()
            if node:
                node.enabled = enabled
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()

    def delete(self, node_id: str) -> None:
        session = self._get_session()
        try:
            # Delete associated edges
            session.query(EdgeModel).filter((EdgeModel.source_node == node_id) | (EdgeModel.target_node == node_id)).delete()
            node = session.query(NodeModel).filter(NodeModel.id == node_id).first()
            if node:
                session.delete(node)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()

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
