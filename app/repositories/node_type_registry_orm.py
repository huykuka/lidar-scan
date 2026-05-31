"""Repository for the node_type_registry table."""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models import NodeTypeRegistryModel
from app.db.session import SessionLocal


class NodeTypeRegistryRepository:
    """CRUD for the ``node_type_registry`` table.

    Follows the same optional-session pattern as NodeRepository.
    """

    def __init__(self, session: Optional[Session] = None) -> None:
        self._session = session

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        from app.db.session import get_engine
        get_engine()
        return SessionLocal()

    def _should_close(self) -> bool:
        return self._session is None

    def list_all(self) -> List[Dict[str, object]]:
        """Return all registered node types with their enabled state."""
        session = self._get_session()
        try:
            rows = session.query(NodeTypeRegistryModel).all()
            return [r.to_dict() for r in rows]
        finally:
            if self._should_close():
                session.close()

    def get_enabled_types(self) -> set[str]:
        """Return the set of node type strings that are enabled."""
        session = self._get_session()
        try:
            rows = (
                session.query(NodeTypeRegistryModel.type)
                .filter(NodeTypeRegistryModel.enabled.is_(True))
                .all()
            )
            return {r[0] for r in rows}
        finally:
            if self._should_close():
                session.close()

    def is_enabled(self, node_type: str) -> bool:
        """Check if a specific node type is enabled.  Defaults to True if not in DB."""
        session = self._get_session()
        try:
            row = (
                session.query(NodeTypeRegistryModel)
                .filter(NodeTypeRegistryModel.type == node_type)
                .first()
            )
            return row.enabled if row else True
        finally:
            if self._should_close():
                session.close()

    def set_enabled(self, node_type: str, enabled: bool) -> None:
        """Set the enabled state for a node type (upsert)."""
        session = self._get_session()
        try:
            row = (
                session.query(NodeTypeRegistryModel)
                .filter(NodeTypeRegistryModel.type == node_type)
                .first()
            )
            if row:
                row.enabled = enabled
            else:
                session.add(NodeTypeRegistryModel(type=node_type, enabled=enabled))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()

    def seed_from_definitions(self, types: List[str]) -> None:
        """Ensure every known node type has a row.  New types default to enabled."""
        session = self._get_session()
        try:
            existing = {
                r[0]
                for r in session.query(NodeTypeRegistryModel.type).all()
            }
            for t in types:
                if t not in existing:
                    session.add(NodeTypeRegistryModel(type=t, enabled=True))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if self._should_close():
                session.close()
