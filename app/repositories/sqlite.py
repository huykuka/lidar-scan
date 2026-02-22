import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


DB_PATH = Path("config/data.db")


def _ensure_db_dir() -> None:
    os.makedirs(DB_PATH.parent, exist_ok=True)


@contextmanager
def db_conn() -> Iterator[sqlite3.Connection]:
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_schema() -> None:
    with db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lidars (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                launch_args TEXT NOT NULL,
                pipeline_name TEXT,
                mode TEXT DEFAULT 'real',
                pcd_path TEXT,
                x REAL DEFAULT 0,
                y REAL DEFAULT 0,
                z REAL DEFAULT 0,
                roll REAL DEFAULT 0,
                pitch REAL DEFAULT 0,
                yaw REAL DEFAULT 0
            )
            """
        )

        # Lightweight migrations
        cols = {row[1] for row in conn.execute("PRAGMA table_info(lidars)").fetchall()}
        if "enabled" not in cols:
            conn.execute("ALTER TABLE lidars ADD COLUMN enabled INTEGER DEFAULT 1")

        cols = {row[1] for row in conn.execute("PRAGMA table_info(lidars)").fetchall()}
        if "topic_prefix" not in cols:
            conn.execute("ALTER TABLE lidars ADD COLUMN topic_prefix TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fusions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                topic TEXT NOT NULL,
                sensor_ids TEXT NOT NULL,
                pipeline_name TEXT
            )
            """
        )

        fcols = {row[1] for row in conn.execute("PRAGMA table_info(fusions)").fetchall()}
        if "enabled" not in fcols:
            conn.execute("ALTER TABLE fusions ADD COLUMN enabled INTEGER DEFAULT 1")

        # Backfill lidar.topic_prefix for existing rows
        # Keep it URL-friendly and stable; avoid collisions.
        lrows = conn.execute(
            "SELECT id, name, topic_prefix FROM lidars ORDER BY rowid ASC"
        ).fetchall()
        in_use: set[str] = set()
        for r in lrows:
            existing = (r[2] or "").strip()
            if existing:
                in_use.add(existing)

        def _slugify(val: str) -> str:
            import re

            base = re.sub(r"[^A-Za-z0-9_-]+", "_", (val or "").strip())
            base = re.sub(r"_+", "_", base).strip("_-")
            return base or "sensor"

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
                "UPDATE lidars SET topic_prefix = ? WHERE id = ?",
                (topic_prefix, sensor_id),
            )
        conn.commit()


def new_id() -> str:
    return uuid.uuid4().hex


def dumps_json(value: Any) -> str:
    return json.dumps(value)


def loads_json(value: str) -> Any:
    return json.loads(value)


init_schema()
