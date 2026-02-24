"""SQLAlchemy engine + session initialization.

We keep engine creation out of model import time so tests can override the DB
location without fighting module-level globals.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


DB_PATH = Path("config/data.db")

SessionLocal = sessionmaker(autocommit=False, autoflush=False)
_engine: Optional[Engine] = None


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

    _engine = create_engine(database_url, connect_args={"check_same_thread": False})
    SessionLocal.configure(bind=_engine)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return init_engine()
    return _engine
