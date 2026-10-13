#!/usr/bin/env python3
"""Convert legacy ZIP (PCD) recordings to MCAP and repoint the database.

For every recording row whose ``file_path`` ends in ``.zip``:
  1. convert it to ``<same stem>.mcap`` (foxglove.PointCloud messages),
  2. verify the frame count of the result,
  3. update ``file_path`` / ``file_size_bytes`` in the database,
  4. optionally delete the original ZIP.

Thumbnails share the file stem, so they keep working untouched.

Usage (from the project root):
    uv run python scripts/migrate_recordings_to_mcap.py --dry-run
    uv run python scripts/migrate_recordings_to_mcap.py
    uv run python scripts/migrate_recordings_to_mcap.py --delete-originals

Back up ``data/recordings`` and ``data/config/data.db`` before the first real run.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import RecordingModel  # noqa: E402
from app.db.session import SessionLocal, init_engine  # noqa: E402
from app.services.shared.recording import McapRecordingReader, convert_zip_to_mcap  # noqa: E402

logger = logging.getLogger("migrate_recordings_to_mcap")


def _convert(src: Path, dest: Path) -> int:
    """Convert src -> dest atomically; return the verified frame count."""
    partial = dest.with_name(f"{dest.stem}.partial.mcap")
    partial.unlink(missing_ok=True)
    try:
        info = convert_zip_to_mcap(src, partial)
        reader = McapRecordingReader(partial)
        try:
            if reader.frame_count != info["frame_count"]:
                raise ValueError(
                    f"frame count mismatch after conversion: {reader.frame_count} != {info['frame_count']}"
                )
        finally:
            reader.close()
        partial.replace(dest)
        return info["frame_count"]
    finally:
        partial.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="show what would be converted, change nothing")
    parser.add_argument("--delete-originals", action="store_true", help="delete each ZIP after a verified conversion")
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite DB path (default: data/config/data.db)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_engine(db_path=args.db_path)

    converted = skipped = failed = 0
    session = SessionLocal()
    try:
        rows = session.query(RecordingModel).filter(RecordingModel.file_path.like("%.zip")).all()
        logger.info("%d legacy ZIP recording(s) found", len(rows))

        for row in rows:
            src = Path(row.file_path)
            dest = src.with_suffix(".mcap")
            if row.status != "ready":
                logger.warning("skip %s: status=%s", row.id, row.status)
                skipped += 1
                continue
            if not src.exists() and not dest.exists():
                logger.warning("skip %s: file missing (%s)", row.id, src)
                skipped += 1
                continue
            if args.dry_run:
                logger.info("[dry-run] %s -> %s", src, dest.name)
                continue

            try:
                if dest.exists():
                    reader = McapRecordingReader(dest)
                    reader.close()
                    logger.info("%s already converted, repointing DB", dest.name)
                else:
                    frames = _convert(src, dest)
                    logger.info("converted %s (%d frames)", src.name, frames)
                row.file_path = str(dest)
                row.file_size_bytes = dest.stat().st_size
                session.commit()
                if args.delete_originals and src.exists():
                    src.unlink()
                converted += 1
            except Exception as exc:
                session.rollback()
                logger.error("failed %s (%s): %s", row.id, src.name, exc)
                failed += 1
    finally:
        session.close()

    logger.info("done: %d converted, %d skipped, %d failed", converted, skipped, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
