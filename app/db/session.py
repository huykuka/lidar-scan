"""SQLAlchemy engine + session initialization.

We keep engine creation out of model import time so tests can override the DB
location without fighting module-level globals.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

DB_PATH = Path("data/config/data.db")

SessionLocal = sessionmaker(autocommit=False, autoflush=False)
_engine: Optional[Engine] = None

# SQLite performance pragmas applied on every new connection.
# Critical for Docker deployments where the overlay2 filesystem makes
# fsync ~5-10x slower than native ext4.  WAL mode eliminates the
# rollback-journal fsync storm and allows concurrent readers.
_SQLITE_PRAGMAS = [
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("cache_size", -64000),  # 64 MB page cache (negative = KiB)
    ("mmap_size", 268435456),  # 256 MB memory-mapped I/O
    ("busy_timeout", 5000),  # wait up to 5 s instead of immediate SQLITE_BUSY
    ("journal_size_limit", 67108864),  # cap WAL file at 64 MB
    ("temp_store", "MEMORY"),
]


def _set_sqlite_pragmas(dbapi_conn, connection_record):
    """Event listener: configure pragmas on every new SQLite connection."""
    cursor = dbapi_conn.cursor()
    for pragma, value in _SQLITE_PRAGMAS:
        cursor.execute(f"PRAGMA {pragma}={value}")
    cursor.close()


def init_engine(database_url: str | None = None, *, db_path: Path | None = None) -> Engine:
    """Initialize (or re-initialize) the global SQLAlchemy engine."""

    global _engine

    if database_url is None:
        database_url = os.getenv("DATABASE_URL")

    if database_url is None:
        path = db_path or DB_PATH
        os.makedirs(path.parent, exist_ok=True)
        database_url = f"sqlite:///{path}"

    if _engine is not None:
        _engine.dispose()

    _engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        pool_size=4,
        pool_pre_ping=True,
    )

    # Apply SQLite-specific pragmas when the URL targets a SQLite database.
    if database_url.startswith("sqlite"):
        event.listen(_engine, "connect", _set_sqlite_pragmas)

    SessionLocal.configure(bind=_engine)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return init_engine()
    return _engine
