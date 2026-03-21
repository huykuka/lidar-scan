"""TDD Tests for DagMetaRepository.

Tests written BEFORE implementation (TDD phase).
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


class TestDagMetaRepository:
    """Unit tests for DagMetaRepository"""

    def test_get_version_returns_0_for_fresh_db(self, client):
        """A freshly migrated DB must return config_version=0."""
        from app.repositories.dag_meta_orm import DagMetaRepository
        repo = DagMetaRepository()
        assert repo.get_version() == 0

    def test_increment_version_returns_new_value(self, client):
        """increment_version() must return 1 when called on version=0."""
        from app.repositories.dag_meta_orm import DagMetaRepository
        session = SessionLocal()
        try:
            repo = DagMetaRepository(session=session)
            new_ver = repo.increment_version(session)
            session.commit()
            assert new_ver == 1
        finally:
            session.close()

    def test_increment_version_is_atomic(self, client):
        """Two sequential increment calls must return 1 then 2."""
        from app.repositories.dag_meta_orm import DagMetaRepository
        session = SessionLocal()
        try:
            repo = DagMetaRepository(session=session)
            v1 = repo.increment_version(session)
            session.commit()
            v2 = repo.increment_version(session)
            session.commit()
            assert v1 == 1
            assert v2 == 2
        finally:
            session.close()
