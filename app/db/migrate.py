"""Lightweight SQLite migrations for the ORM schema.

We intentionally keep this minimal (no Alembic) to match the project's current
setup and to support existing `config/data.db` files.
"""

from __future__ import annotations

import json
import re
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.models import Base

_POSE_KEYS = {"x", "y", "z", "roll", "pitch", "yaw"}


def _table_cols(conn, table: str) -> set[str]:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
    return {r[1] for r in rows}


def _slugify(val: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", (val or "").strip())
    base = re.sub(r"_+", "_", base).strip("_-")
    return base or "sensor"


def _backfill_pose_into_config(conn) -> None:
    """Idempotent data-only migration: move flat pose keys into config["pose"].

    For each row in the ``nodes`` table:
    - Skip rows that already have ``config["pose"]`` (idempotent).
    - For rows with flat pose keys (x, y, z, roll, pitch, yaw) at the TOP
      LEVEL of ``config_json``, migrate them into a nested ``config["pose"]``
      dict and remove the flat keys.
    - Writes the updated ``config_json`` back.

    No DDL / ALTER TABLE is performed.
    """
    rows = conn.execute(text("SELECT id, config FROM nodes")).fetchall()
    for row_id, config_raw in rows:
        try:
            cfg = json.loads(config_raw) if config_raw else {}
        except (json.JSONDecodeError, TypeError):
            cfg = {}

        # Already migrated — skip
        if "pose" in cfg:
            continue

        # Check for flat pose keys at top level
        flat_pose = {k: cfg[k] for k in _POSE_KEYS if k in cfg}
        if not flat_pose:
            continue

        # Build nested pose dict (fill missing keys with 0.0)
        nested_pose = {k: float(flat_pose.get(k, 0.0)) for k in _POSE_KEYS}

        # Remove flat keys and add nested pose
        for k in _POSE_KEYS:
            cfg.pop(k, None)
        cfg["pose"] = nested_pose

        conn.execute(
            text("UPDATE nodes SET config = :cfg WHERE id = :id"),
            {"cfg": json.dumps(cfg), "id": row_id},
        )


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
        
        # Backfill flat pose keys into nested config["pose"] (data-only, no DDL)
        _backfill_pose_into_config(conn)
