"""
Repository for node persistence using SQLAlchemy ORM.
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
        """Get all nodes from database"""
        session = self._get_session()
        try:
            nodes = session.query(NodeModel).all()
            return [node.to_dict() for node in nodes]
        finally:
            if self._should_close():
                session.close()
    
    def get_by_id(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get a single node by ID"""
        session = self._get_session()
        try:
            node = session.query(NodeModel).filter(NodeModel.id == node_id).first()
            return node.to_dict() if node else None
        finally:
            if self._should_close():
                session.close()
                
    def upsert(self, data: Dict[str, Any]) -> str:
        """Create or update a node"""
        session = self._get_session()
        try:
            record_id = data.get("id") or uuid.uuid4().hex
            config_str = json.dumps(data.get("config", {}))
            enabled = data.get("enabled", True)
            x = data.get("x", 100.0)
            y = data.get("y", 100.0)
            
            existing = session.query(NodeModel).filter(NodeModel.id == record_id).first()
            if existing:
                existing.name = data.get("name", existing.name)
                existing.type = data.get("type", existing.type)
                existing.category = data.get("category", existing.category)
                existing.enabled = data.get("enabled", existing.enabled)
                if "config" in data:
                    existing.config_json = config_str
                if "x" in data:
                    existing.x = data["x"]
                if "y" in data:
                    existing.y = data["y"]
            else:
                node = NodeModel(
                    id=record_id,
                    name=data.get("name", ""),
                    type=data.get("type", ""),
                    category=data.get("category", ""),
                    enabled=enabled,
                    config_json=config_str,
                    x=x,
                    y=y
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
        """Toggle node enabled state"""
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
        """Delete a node and its associated edges"""
        session = self._get_session()
        try:
            # Delete associated edges
            session.query(EdgeModel).filter(
                (EdgeModel.source_node == node_id) | (EdgeModel.target_node == node_id)
            ).delete()
            
            # Delete the node
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
    
    def update_node_config(self, node_id: str, config: Dict[str, Any]) -> None:
        """Update node configuration"""
        session = self._get_session()
        try:
            node = session.query(NodeModel).filter(NodeModel.id == node_id).first()
            if node:
                node.config_json = json.dumps(config)
                session.commit()
            else:
                raise ValueError(f"Node {node_id} not found")
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()
