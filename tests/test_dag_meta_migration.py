"""TDD Tests for ensure_schema() migration — dag_meta table.

Tests written BEFORE implementation (TDD phase).
"""

from __future__ import annotations

import pytest


class TestDagMetaMigration:
    """Tests verifying dag_meta table creation and seeding via ensure_schema()."""

    def test_dag_meta_table_exists_after_ensure_schema(self, client):
        """After ensure_schema(), dag_meta table must exist with 1 row."""
        from app.db.session import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            rows = session.execute(
                text("SELECT id, config_version FROM dag_meta WHERE id = 1")
            ).fetchall()
            assert len(rows) == 1
            row_id, config_version = rows[0]
            assert row_id == 1
            assert config_version == 0
        finally:
            session.close()

    def test_ensure_schema_is_idempotent(self, client):
        """Running ensure_schema() a second time must not create duplicate rows."""
        from app.db.migrate import ensure_schema
        from app.db.session import get_engine, SessionLocal
        from sqlalchemy import text

        engine = get_engine()
        # Run again — must be idempotent
        ensure_schema(engine)

        session = SessionLocal()
        try:
            count = session.execute(
                text("SELECT COUNT(*) FROM dag_meta")
            ).scalar()
            assert count == 1
        finally:
            session.close()
