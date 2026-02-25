"""Lightweight SQLite migrations for the ORM schema.

We intentionally keep this minimal (no Alembic) to match the project's current
setup and to support existing `config/data.db` files.
"""

from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.models import Base


def _table_cols(conn, table: str) -> set[str]:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
    return {r[1] for r in rows}


def _slugify(val: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", (val or "").strip())
    base = re.sub(r"_+", "_", base).strip("_-")
    return base or "sensor"


def ensure_schema(engine: Engine) -> None:
    """Create tables + apply additive migrations/backfills."""

    # Create missing tables first.
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        # We start with a clean slate for the node architecture, so 
        # legacy migrations for lidars and fusions have been removed.
        pass
