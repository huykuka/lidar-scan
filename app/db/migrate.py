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
        # Add visible column if it doesn't exist
        if "visible" not in _table_cols(conn, "nodes"):
            conn.execute(text("ALTER TABLE nodes ADD COLUMN visible INTEGER NOT NULL DEFAULT 1"))
        
        # Add provenance tracking columns to calibration_history (ICP Flow Alignment feature)
        cal_cols = _table_cols(conn, "calibration_history")
        if "source_sensor_id" not in cal_cols:
            conn.execute(text("ALTER TABLE calibration_history ADD COLUMN source_sensor_id TEXT"))
        if "processing_chain_json" not in cal_cols:
            conn.execute(text("ALTER TABLE calibration_history ADD COLUMN processing_chain_json TEXT NOT NULL DEFAULT '[]'"))
        if "run_id" not in cal_cols:
            conn.execute(text("ALTER TABLE calibration_history ADD COLUMN run_id TEXT"))
        
        # We start with a clean slate for the node architecture, so 
        # legacy migrations for lidars and fusions have been removed.
        pass
