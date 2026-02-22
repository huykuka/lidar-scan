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
        conn.commit()


def new_id() -> str:
    return uuid.uuid4().hex


def dumps_json(value: Any) -> str:
    return json.dumps(value)


def loads_json(value: str) -> Any:
    return json.loads(value)


init_schema()
