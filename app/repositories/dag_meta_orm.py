"""Repository for the dag_meta single-row versioning table."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


class DagMetaRepository:
    """Repository for reading and incrementing the DAG config version.

    Follows the same optional-session pattern as NodeRepository / EdgeRepository:
    - If constructed with a ``Session``, the caller owns commit/rollback.
    - Otherwise a new session is opened and closed around each call.
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

    def get_version(self) -> int:
        """Return the current ``config_version`` from the dag_meta row."""
        session = self._get_session()
        try:
            row = session.execute(
                text("SELECT config_version FROM dag_meta WHERE id = 1")
            ).fetchone()
            if row is None:
                return 0
            return int(row[0])
        finally:
            if self._should_close():
                session.close()

    def increment_version(self, session: Session) -> int:
        """Increment ``config_version`` by 1 and return the new value.

        Must be called within an **open transaction** owned by the caller.
        The caller is responsible for committing the transaction.

        Args:
            session: The active SQLAlchemy session to use for the UPDATE.

        Returns:
            The new (incremented) ``config_version``.
        """
        session.execute(
            text(
                "UPDATE dag_meta SET config_version = config_version + 1 WHERE id = 1"
            )
        )
        row = session.execute(
            text("SELECT config_version FROM dag_meta WHERE id = 1")
        ).fetchone()
        return int(row[0]) if row else 1
