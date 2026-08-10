"""Lightweight SQLite migrations for the ORM schema.

We intentionally keep this minimal (no Alembic) to match the project's current
setup and to support existing `config/data.db` files.
"""

from __future__ import annotations

import errno
import glob
import json
import logging
import os
import re
import time

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.models import Base
from app.db.session import SessionLocal

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


def _seed_default_users() -> None:
    """Create default admin and user accounts if the users table is empty."""
    import uuid
    import bcrypt
    from app.db.models import UserModel

    session = SessionLocal()
    try:
        count = session.query(UserModel).count()
        if count > 0:
            return

        defaults = [
            ("user", "user", "user"),
            ("admin", "admin", "admin"),
            ("service", "service", "service"),
        ]
        for username, password, role in defaults:
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            session.add(
                UserModel(
                    id=str(uuid.uuid4()),
                    username=username,
                    password_hash=pw_hash,
                    role=role,
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _seed_node_type_registry() -> None:
    """Seed node_type_registry rows for every discovered definition.

    New types default to enabled.  Existing rows are not touched so that
    admin disable decisions are preserved across restarts.
    """
    from app.repositories.node_type_registry_orm import NodeTypeRegistryRepository
    from app.services.nodes.schema import node_schema_registry

    all_types = [d.type for d in node_schema_registry.get_all()]
    if all_types:
        NodeTypeRegistryRepository().seed_from_definitions(all_types)


def ensure_schema(engine: Engine) -> None:
    """Create tables + apply additive migrations/backfills."""

    # Create missing tables first.
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        # Add visible column if it doesn't exist
        if "visible" not in _table_cols(conn, "nodes"):
            conn.execute(
                text("ALTER TABLE nodes ADD COLUMN visible INTEGER NOT NULL DEFAULT 1")
            )

        # Add provenance tracking columns to calibration_history (ICP Flow Alignment feature)
        cal_cols = _table_cols(conn, "calibration_history")
        if "source_sensor_id" not in cal_cols:
            conn.execute(
                text("ALTER TABLE calibration_history ADD COLUMN source_sensor_id TEXT")
            )
        if "processing_chain_json" not in cal_cols:
            conn.execute(
                text(
                    "ALTER TABLE calibration_history ADD COLUMN processing_chain_json TEXT NOT NULL DEFAULT '[]'"
                )
            )
        if "run_id" not in cal_cols:
            conn.execute(text("ALTER TABLE calibration_history ADD COLUMN run_id TEXT"))
        if "node_id" not in cal_cols:
            conn.execute(
                text("ALTER TABLE calibration_history ADD COLUMN node_id TEXT")
            )
        if "accepted_at" not in cal_cols:
            conn.execute(
                text("ALTER TABLE calibration_history ADD COLUMN accepted_at TEXT")
            )
        if "accepted_by" not in cal_cols:
            conn.execute(
                text("ALTER TABLE calibration_history ADD COLUMN accepted_by TEXT")
            )
        if "rollback_source_id" not in cal_cols:
            conn.execute(
                text(
                    "ALTER TABLE calibration_history ADD COLUMN rollback_source_id TEXT"
                )
            )
        if "registration_method_json" not in cal_cols:
            conn.execute(
                text(
                    "ALTER TABLE calibration_history ADD COLUMN registration_method_json TEXT DEFAULT 'null'"
                )
            )

        # Backfill flat pose keys into nested config["pose"] (data-only, no DDL)
        _backfill_pose_into_config(conn)

        # Add status column to recordings (recording-trim feature)
        if "status" not in _table_cols(conn, "recordings"):
            conn.execute(
                text(
                    "ALTER TABLE recordings ADD COLUMN status TEXT NOT NULL DEFAULT 'ready'"
                )
            )

    # Seed dag_meta row if table is empty (idempotent via INSERT OR IGNORE)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT OR IGNORE INTO dag_meta (id, config_version) VALUES (1, 0)")
        )

    # Seed default users (admin/user) if users table is empty
    _seed_default_users()

    # Seed node_type_registry from discovered definitions (all enabled by default)
    _seed_node_type_registry()

    # Add index on application_results if it was created without it (e.g. old DBs)
    with engine.begin() as conn:
        existing_indexes = {
            row[1]
            for row in conn.exec_driver_sql(
                "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='application_results'"
            ).fetchall()
        }
        if "idx_results_node_ts" not in existing_indexes:
            try:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_results_node_ts "
                        "ON application_results(node_id, timestamp DESC)"
                    )
                )
            except Exception:
                pass  # Table may not exist yet on first run; create_all handles it


_migrate_logger = logging.getLogger(__name__)
_RECORDINGS_DIR = "data/recordings"
_LOCK_FILE = "data/recordings/.mcap_migration.lock"
_STALE_AGE_SECONDS = 3600  # 1 hour


def _acquire_migration_lock() -> bool:
    """Try to acquire the migration lock file.  Returns True if acquired."""
    lock_path = _LOCK_FILE
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    # Check for stale lock
    if os.path.exists(lock_path):
        try:
            with open(lock_path) as f:
                content = f.read().strip()
            parts = content.split("|", 1)
            pid = int(parts[0]) if parts else 0
            age = time.time() - os.path.getmtime(lock_path)
            pid_dead = False
            if pid and pid != os.getpid():
                try:
                    os.kill(pid, 0)
                except OSError as e:
                    if e.errno == errno.ESRCH:
                        pid_dead = True
            if pid_dead or age > _STALE_AGE_SECONDS:
                _migrate_logger.warning(
                    "Removing stale migration lock (pid=%d, age=%.0fs)", pid, age
                )
                os.remove(lock_path)
        except Exception:
            pass

    # Atomic O_CREAT|O_EXCL
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        import datetime as _dt
        os.write(fd, f"{os.getpid()}|{_dt.datetime.now().isoformat()}".encode())
        os.close(fd)
        return True
    except OSError as e:
        if e.errno in (errno.EEXIST, errno.EACCES):
            return False
        raise


def _release_migration_lock() -> None:
    try:
        os.remove(_LOCK_FILE)
    except Exception:
        pass


def _is_valid_mcap(path: str, expected_frame_count: int | None = None) -> bool:
    """Return True if *path* is a readable MCAP with correct frame count."""
    try:
        from app.services.shared.mcap_recording import McapRecordingReader as _R
        r = _R(path)
        ok = True
        if expected_frame_count is not None:
            ok = r.frame_count == expected_frame_count
        r.close()
        return ok
    except Exception:
        return False


def migrate_zip_recordings_to_mcap() -> None:
    """Migrate all persisted .zip recording files to MCAP format.

    - Acquires a lock so only one process runs the migration at a time.
    - Cleans up orphaned .mcap.part files before starting.
    - Converts every .zip (both DB-tracked and orphan files).
    - Per-file isolation: a failure on one file does not abort others.
    - Idempotent: already-converted .mcap files with correct frame count are skipped.
    - On success: .zip is deleted, DB file_path updated to .mcap abs path.
    """
    from app.db.session import SessionLocal
    from sqlalchemy import text as _text

    if not _acquire_migration_lock():
        _migrate_logger.info("ZIP→MCAP migration: another process holds the lock, skipping.")
        return

    t0 = time.monotonic()
    converted = 0
    skipped = 0
    failed = 0

    try:
        # --- Pre-scan: delete orphan .mcap.part files ---
        for part in glob.glob(os.path.join(_RECORDINGS_DIR, "*.mcap.part")):
            try:
                os.remove(part)
                _migrate_logger.info("Removed orphan part file: %s", part)
            except Exception as e:
                _migrate_logger.warning("Could not remove orphan part file %s: %s", part, e)

        # --- Collect candidates from DB ---
        db_rows: list[tuple[str, str]] = []  # (id, file_path)
        try:
            with SessionLocal() as sess:
                rows = sess.execute(_text("SELECT id, file_path FROM recordings")).fetchall()
                db_rows = [(str(r[0]), str(r[1])) for r in rows]
        except Exception as e:
            _migrate_logger.error("Failed to query recordings table: %s", e)
            return

        # Map from abs zip path → row id for DB update
        zip_rows: dict[str, str] = {}
        for row_id, fpath in db_rows:
            abs_path = os.path.abspath(fpath)
            if abs_path.endswith(".zip"):
                zip_rows[abs_path] = row_id

        # --- Also collect orphan .zip files not in DB ---
        orphan_zips: list[str] = []
        db_abs_paths = {os.path.abspath(fp) for _, fp in db_rows}
        for zp in glob.glob(os.path.join(_RECORDINGS_DIR, "*.zip")):
            abs_zp = os.path.abspath(zp)
            if abs_zp not in db_abs_paths:
                orphan_zips.append(abs_zp)

        all_zips: list[tuple[str, str | None]] = [
            (zp, row_id) for zp, row_id in zip_rows.items()
        ] + [(zp, None) for zp in orphan_zips]

        if not all_zips:
            _migrate_logger.info("ZIP→MCAP migration: no .zip recordings found, nothing to do.")
            return

        _migrate_logger.info("ZIP→MCAP migration: found %d .zip file(s) to process.", len(all_zips))

        for zip_abs, row_id in all_zips:
            _migrate_one_zip(zip_abs, row_id)
            # Count outcome based on whether file was converted or skipped
            # (outcomes set inside _migrate_one_zip but we track via log)

        elapsed = time.monotonic() - t0
        _migrate_logger.info(
            "ZIP→MCAP migration complete. Elapsed: %.1fs, processed %d file(s).",
            elapsed, len(all_zips),
        )

    finally:
        _release_migration_lock()


def _migrate_one_zip(zip_abs: str, row_id: str | None) -> None:
    """Migrate a single .zip file to .mcap.  Isolated per-file try/except."""
    from app.services.shared.mcap_recording import (
        McapRecordingWriter as _MWriter,
        McapRecordingReader as _MReader,
        _ZipRecordingReader as _ZipShim,
    )
    from app.db.session import SessionLocal
    from sqlalchemy import text as _text

    stem = os.path.splitext(zip_abs)[0]
    mcap_abs = stem + ".mcap"
    part_abs = stem + ".mcap.part"

    try:
        # 1. Check source exists
        if not os.path.exists(zip_abs):
            _migrate_logger.warning("ZIP not on disk (skipping): %s", zip_abs)
            return

        # 2. Open source to get frame count
        try:
            zip_reader = _ZipShim(zip_abs)
            source_frame_count = zip_reader.frame_count
            source_meta = dict(zip_reader.metadata)
        except Exception as e:
            _migrate_logger.error("Cannot read source ZIP %s: %s — retaining as-is.", zip_abs, e)
            return

        # 3. Check if target .mcap already exists and is valid
        if os.path.exists(mcap_abs):
            if _is_valid_mcap(mcap_abs, expected_frame_count=source_frame_count):
                _migrate_logger.debug("Already converted (skipping re-encode): %s", mcap_abs)
                # Still fix DB row if needed
                if row_id:
                    _update_db_row(row_id, mcap_abs)
                # Delete source .zip
                try:
                    os.remove(zip_abs)
                except Exception as e:
                    _migrate_logger.warning("Could not delete .zip after valid .mcap found: %s", e)
                return
            else:
                _migrate_logger.warning(
                    "Existing .mcap invalid or wrong frame count, re-migrating: %s", mcap_abs
                )
                try:
                    os.remove(mcap_abs)
                except Exception:
                    pass

        # 4. Write .mcap.part
        try:
            writer = _MWriter(part_abs, source_meta)
            writer.write_batch(list(zip_reader.iter_frames()))
            writer.finalize()
            zip_reader.close()
        except Exception as e:
            _migrate_logger.error("Failed writing .mcap.part for %s: %s", zip_abs, e)
            _try_remove(part_abs)
            return

        # 5. Validate .part (frame count + read first+last)
        try:
            part_reader = _MReader(part_abs)
            ok = (part_reader.frame_count == source_frame_count)
            if ok and source_frame_count > 0:
                part_reader.get_frame(0)
                if source_frame_count > 1:
                    part_reader.get_frame(source_frame_count - 1)
            part_reader.close()
            if not ok:
                raise ValueError(
                    f"frame_count mismatch: part={part_reader.frame_count} source={source_frame_count}"
                )
        except Exception as e:
            _migrate_logger.error("Validation of .mcap.part failed for %s: %s", zip_abs, e)
            _try_remove(part_abs)
            return

        # 6. Atomic replace
        os.replace(part_abs, mcap_abs)

        # 7. Update DB row
        if row_id:
            _update_db_row(row_id, mcap_abs)

        # 8. Delete source .zip
        try:
            os.remove(zip_abs)
        except Exception as e:
            _migrate_logger.warning("Could not delete source .zip %s: %s", zip_abs, e)

        _migrate_logger.info(
            "Migrated: %s → %s (%d frames)", zip_abs, mcap_abs, source_frame_count
        )

    except Exception as exc:
        _migrate_logger.error(
            "Unexpected error migrating %s: %s — retaining .zip.", zip_abs, exc, exc_info=True
        )
        _try_remove(part_abs)


def _update_db_row(row_id: str, mcap_abs: str) -> None:
    from app.db.session import SessionLocal
    from sqlalchemy import text as _text

    try:
        with SessionLocal() as sess:
            sess.execute(
                _text("UPDATE recordings SET file_path = :fp WHERE id = :id"),
                {"fp": mcap_abs, "id": row_id},
            )
            sess.commit()
    except Exception as e:
        _migrate_logger.error("DB update failed for row %s → %s: %s", row_id, mcap_abs, e)


def _try_remove(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
