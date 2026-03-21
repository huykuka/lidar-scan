"""
Repository for node persistence using SQLAlchemy ORM.
"""
import json
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.db.models import NodeModel, EdgeModel
from app.db.session import SessionLocal
from app.schemas.pose import Pose

# Deprecated flat pose keys that must NOT appear inside config{}
_FLAT_POSE_KEYS = frozenset({"x", "y", "z", "roll", "pitch", "yaw"})


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
        """Create or update a node.

        Raises ``ValueError`` if deprecated flat pose keys (x, y, z, roll,
        pitch, yaw) are present inside the ``config`` sub-dict.  Pose must be
        supplied as a top-level ``"pose"`` key or omitted entirely.
        """
        # --- Guard: reject flat pose keys inside config ----------------------
        incoming_config: Dict[str, Any] = data.get("config", {}) or {}
        bad_keys = _FLAT_POSE_KEYS & set(incoming_config.keys())
        if bad_keys:
            raise ValueError(
                f"Deprecated flat pose keys in config: {sorted(bad_keys)}. "
                "Use the top-level 'pose' object instead."
            )

        session = self._get_session()
        try:
            record_id = data.get("id") or uuid.uuid4().hex
            enabled = data.get("enabled", True)
            visible = data.get("visible", True)
            x = data.get("x", 100.0)
            y = data.get("y", 100.0)

            # --- Merge pose into config_json ----------------------------------
            # If caller provides a top-level "pose" dict/Pose, store it nested
            # inside config_json["pose"] so the DB layer stays schema-free.
            raw_pose = data.get("pose")

            existing = session.query(NodeModel).filter(NodeModel.id == record_id).first()
            if existing:
                existing.name = data.get("name", existing.name)
                existing.type = data.get("type", existing.type)
                existing.category = data.get("category", existing.category)
                existing.enabled = data.get("enabled", existing.enabled)
                existing.visible = data.get("visible", existing.visible)
                if "config" in data or raw_pose is not None:
                    # Re-read existing config to merge into it
                    stored_config: Dict[str, Any] = json.loads(existing.config_json) if existing.config_json else {}
                    if "config" in data:
                        stored_config.update(incoming_config)
                    if raw_pose is not None:
                        pose_dict = raw_pose if isinstance(raw_pose, dict) else raw_pose.to_flat_dict()
                        stored_config["pose"] = pose_dict
                    existing.config_json = json.dumps(stored_config)
                if "x" in data and data["x"] is not None:
                    existing.x = data["x"]
                if "y" in data and data["y"] is not None:
                    existing.y = data["y"]
            else:
                # Build initial config blob
                config_blob: Dict[str, Any] = dict(incoming_config)
                if raw_pose is not None:
                    pose_dict = raw_pose if isinstance(raw_pose, dict) else raw_pose.to_flat_dict()
                    config_blob["pose"] = pose_dict
                node = NodeModel(
                    id=record_id,
                    name=data.get("name", ""),
                    type=data.get("type", ""),
                    category=data.get("category", ""),
                    enabled=enabled,
                    visible=visible,
                    config_json=json.dumps(config_blob),
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

    def set_visible(self, node_id: str, visible: bool) -> None:
        """Toggle node visible state"""
        session = self._get_session()
        try:
            node = session.query(NodeModel).filter(NodeModel.id == node_id).first()
            if not node:
                raise ValueError(f"Node {node_id} not found")
            node.visible = visible
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

    def update_node_pose(self, node_id: str, pose: Pose) -> None:
        """Update only the pose sub-object inside a node's config_json.

        Reads the existing config blob, replaces (or inserts) the ``"pose"``
        key with ``pose.to_flat_dict()``, and writes it back atomically.
        Raises ``ValueError`` when the node does not exist.
        """
        session = self._get_session()
        try:
            node = session.query(NodeModel).filter(NodeModel.id == node_id).first()
            if not node:
                raise ValueError(f"Node {node_id} not found")
            config: Dict[str, Any] = json.loads(node.config_json) if node.config_json else {}
            config["pose"] = pose.to_flat_dict()
            node.config_json = json.dumps(config)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()
