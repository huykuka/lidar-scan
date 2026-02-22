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
        # Additive migrations for existing DBs.
        if "lidars" in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='lidars'"
        ).fetchall():
            pass

        lidar_cols = _table_cols(conn, "lidars")
        if "enabled" not in lidar_cols:
            conn.exec_driver_sql("ALTER TABLE lidars ADD COLUMN enabled BOOLEAN DEFAULT 1")
        if "topic_prefix" not in lidar_cols:
            conn.exec_driver_sql("ALTER TABLE lidars ADD COLUMN topic_prefix TEXT")

        fusion_cols = _table_cols(conn, "fusions")
        if "enabled" not in fusion_cols:
            conn.exec_driver_sql("ALTER TABLE fusions ADD COLUMN enabled BOOLEAN DEFAULT 1")

        # Backfill lidar.topic_prefix for existing rows (stable + collision-safe).
        lrows = conn.exec_driver_sql(
            "SELECT id, name, topic_prefix FROM lidars ORDER BY rowid ASC"
        ).fetchall()

        in_use: set[str] = set()
        for r in lrows:
            existing = (r[2] or "").strip()
            if existing:
                in_use.add(existing)

        def _unique(desired: str, sensor_id: str) -> str:
            base = _slugify(desired)
            if base not in in_use:
                in_use.add(base)
                return base

            suffix = _slugify(sensor_id)[:8]
            candidate = f"{base}_{suffix}" if suffix else f"{base}_1"
            i = 2
            while candidate in in_use:
                candidate = f"{base}_{suffix}_{i}" if suffix else f"{base}_{i}"
                i += 1
            in_use.add(candidate)
            return candidate

        for r in lrows:
            if (r[2] or "").strip():
                continue
            sensor_id = r[0]
            name = r[1] or sensor_id
            topic_prefix = _unique(name, sensor_id=sensor_id)
            conn.execute(
                text("UPDATE lidars SET topic_prefix = :topic_prefix WHERE id = :id"),
                {"topic_prefix": topic_prefix, "id": sensor_id},
            )
