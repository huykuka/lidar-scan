"""
ResultsStorageService — persistent storage for application node results.

Architecture:
    - Main system DB (SQLAlchemy ORM, via app.db.session.SessionLocal).
    - PCD files written to disk via asyncio.to_thread (Open3D binary).
    - threading.Lock per node_id for concurrent write safety.
    - Orphan sweep run at startup to delete disk dirs with no DB record.

Migration note: Schema is managed by app.db.migrate.ensure_schema (called at startup).
No separate SQLite DB is created by this service.

Spec: .opencode/plans/application-results-storage/technical.md
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import open3d as o3d
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import cast as _cast

from app.db.models import ApplicationResultModel
from app.db.session import SessionLocal
from app.schemas.results import (
    NodeResultSummary,
    PcdFileEntry,
    ResultDetail,
    ResultSummary,
)

logger = logging.getLogger(__name__)

# Hard-coded limits (can be overridden in tests via instance attribute)
_DEFAULT_MAX_PCD_BYTES: int = 50 * 1024 * 1024  # 50 MB
_DISK_QUOTA_WARN_BYTES: int = 10 * 1024 * 1024 * 1024  # 10 GB
_RESULTS_BASE: str = "data/results"


class ResultsStorageService:
    """Singleton-friendly service for saving and retrieving application node results.

    Uses the main system database (SQLAlchemy ORM / SessionLocal).  Schema is
    created by ``app.db.migrate.ensure_schema`` at application startup — no inline
    DDL is run here.

    Usage pattern in a node's ``on_input()``:
    ::

        result_id = await self._results_service.save_result(
            node_id=self.id,
            pcds=[("empty", empty_pcd), ("loaded", loaded_pcd), ("merged", merged_pcd)],
            metadata={
                "volume_m3": result.volume_m3,
                "icp_fitness": result.icp_fitness,
                "icp_valid": result.icp_valid,
            },
            status="warning" if not result.icp_valid else "success",
        )

    Nodes are responsible for applying RGB colours to their ``PointCloud`` objects
    **before** passing them here.  The service writes binary little-endian PCD via
    ``open3d.io.write_point_cloud(write_ascii=False)``.
    """

    def __init__(self) -> None:
        self._results_base: Path = Path(_RESULTS_BASE)
        self._max_pcd_bytes: int = _DEFAULT_MAX_PCD_BYTES

        # Per-node asyncio locks (created on demand) for concurrent write safety.
        # asyncio.Lock is used instead of threading.Lock to avoid blocking the event loop
        # when multiple coroutines save results for the same node concurrently.
        self._node_locks: Dict[str, asyncio.Lock] = {}
        self._locks_meta_lock = (
            threading.Lock()
        )  # only guards _node_locks dict creation

        self._log_disk_usage()

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _get_session(self) -> Session:
        """Return a new SQLAlchemy session from the main SessionLocal."""
        return SessionLocal()

    def _get_node_lock(self, node_id: str) -> asyncio.Lock:
        with self._locks_meta_lock:
            if node_id not in self._node_locks:
                self._node_locks[node_id] = asyncio.Lock()
            return self._node_locks[node_id]

    def _log_disk_usage(self) -> None:
        try:
            base = Path(_RESULTS_BASE)
            if not base.exists():
                logger.info(
                    "ResultsStorageService: results directory does not exist yet (%s)",
                    base,
                )
                return
            total = sum(f.stat().st_size for f in base.rglob("*") if f.is_file())
            logger.info(
                "ResultsStorageService: disk usage of %s = %.2f MB",
                base,
                total / 1024 / 1024,
            )
            if total > _DISK_QUOTA_WARN_BYTES:
                logger.warning(
                    "ResultsStorageService: disk usage %.2f GB exceeds 10 GB quota warning!",
                    total / 1024 / 1024 / 1024,
                )
        except Exception as exc:
            logger.warning(
                "ResultsStorageService: could not measure disk usage: %s", exc
            )

    @staticmethod
    def _sanitize_label(label: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", label)

    def _result_dir(self, node_id: str, result_id: str) -> Path:
        return Path(_RESULTS_BASE) / node_id / result_id

    def _pcd_url(self, node_id: str, result_id: str, label: str) -> str:
        return (
            f"/api/v1/results/{node_id}/{result_id}/pcd/{self._sanitize_label(label)}"
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def save_result(
        self,
        node_id: str,
        pcds: List[Tuple[str, o3d.geometry.PointCloud]],
        metadata: Dict[str, Any],
        status: Literal["success", "warning", "error"] = "success",
    ) -> str:
        """Persist a set of coloured PCD files and a metadata record.

        Steps:
        1. Create result directory atomically.
        2. Write PCD files via asyncio.to_thread (binary, little-endian).
        3. On disk success: INSERT ORM record inside a DB transaction.
        4. On any failure: shutil.rmtree(result_dir) + re-raise.

        Args:
            node_id:  ID of the application node that produced the result.
            pcds:     List of (label, colored_pcd) tuples. Nodes apply colours before calling.
            metadata: Free-form dict. No validation enforced here.
            status:   "success" | "warning" | "error".

        Returns:
            result_id (UUID4 string).

        Raises:
            ValueError: If any PCD file would exceed the 50 MB size limit.
            IOError:    On disk write failure (after rollback).
        """
        result_id = str(uuid.uuid4())
        result_dir = self._result_dir(node_id, result_id)
        lock = self._get_node_lock(node_id)

        def _write_pcds() -> List[Dict[str, str]]:
            """Runs in a thread via asyncio.to_thread."""
            pcd_entries: List[Dict[str, str]] = []
            os.makedirs(result_dir, exist_ok=True)
            try:
                for label, pcd in pcds:
                    safe_label = self._sanitize_label(label)
                    file_path = result_dir / f"{safe_label}.pcd"
                    o3d.io.write_point_cloud(str(file_path), pcd, write_ascii=False)
                    # Enforce 50 MB limit
                    size = file_path.stat().st_size
                    if size > self._max_pcd_bytes:
                        file_path.unlink(missing_ok=True)
                        raise ValueError(
                            f"PCD file '{safe_label}.pcd' ({size / 1e6:.1f} MB) "
                            f"exceeds {self._max_pcd_bytes / 1e6:.0f} MB limit"
                        )
                    rel_path = str(Path(node_id) / result_id / f"{safe_label}.pcd")
                    pcd_entries.append({"label": safe_label, "path": rel_path})
                return pcd_entries
            except Exception:
                shutil.rmtree(result_dir, ignore_errors=True)
                raise

        try:
            async with lock:
                pcd_entries = await asyncio.to_thread(_write_pcds)

            ts = time.time()
            metadata_json = json.dumps(metadata, default=str)
            pcd_files_json = json.dumps(pcd_entries)

            await asyncio.to_thread(
                self._insert_db_record,
                result_id,
                node_id,
                ts,
                metadata_json,
                pcd_files_json,
                status,
            )
            logger.info(
                "ResultsStorageService: saved result %s for node %s (%d PCDs)",
                result_id,
                node_id,
                len(pcd_entries),
            )
            return result_id
        except Exception:
            # Ensure directory is cleaned if DB insert fails after disk write succeeded
            shutil.rmtree(result_dir, ignore_errors=True)
            raise

    def _insert_db_record(
        self,
        result_id: str,
        node_id: str,
        timestamp: float,
        metadata_json: str,
        pcd_files_json: str,
        status: str,
    ) -> None:
        with self._get_session() as session:
            record = ApplicationResultModel(
                result_id=result_id,
                node_id=node_id,
                timestamp=timestamp,
                metadata_json=metadata_json,
                pcd_files_json=pcd_files_json,
                status=status,
            )
            session.add(record)
            session.commit()

    async def get_node_index(self) -> List[NodeResultSummary]:
        """Return aggregated counts + latest_ts per node_id, for nodes that have results."""
        rows = await asyncio.to_thread(self._query_node_index)
        return [
            NodeResultSummary(
                node_id=node_id,
                node_name=node_id,  # placeholder; API layer merges with DAG name
                node_type="unknown",  # placeholder; API layer fills from DAG
                result_count=cnt,
                latest_timestamp=latest_ts,
            )
            for node_id, cnt, latest_ts in rows
        ]

    def _query_node_index(self) -> List[tuple]:
        with self._get_session() as session:
            rows = (
                session.query(
                    ApplicationResultModel.node_id,
                    func.count(ApplicationResultModel.result_id).label("cnt"),
                    func.max(ApplicationResultModel.timestamp).label("latest_ts"),
                )
                .group_by(ApplicationResultModel.node_id)
                .order_by(func.max(ApplicationResultModel.timestamp).desc())
                .all()
            )
            return [(r.node_id, r.cnt, r.latest_ts) for r in rows]

    async def get_results_by_node(
        self, node_id: str, limit: int = 100, offset: int = 0
    ) -> List[ResultSummary]:
        """Return result summaries for a node, newest first."""
        rows = await asyncio.to_thread(
            self._query_results_by_node, node_id, limit, offset
        )
        summaries: List[ResultSummary] = []
        for row in rows:
            metadata: Dict[str, Any] = (
                json.loads(row.metadata_json) if row.metadata_json else {}
            )
            pcd_files_data: List[Dict[str, str]] = (
                json.loads(row.pcd_files_json) if row.pcd_files_json else []
            )
            # Keep only JSON-primitive scalars (not dicts or lists)
            metadata_summary = {
                k: v
                for k, v in metadata.items()
                if isinstance(v, (str, int, float, bool))
                and not isinstance(v, (dict, list))
            }
            summaries.append(
                ResultSummary(
                    result_id=row.result_id,
                    node_id=row.node_id,
                    timestamp=row.timestamp,
                    status=_cast(Any, row.status),
                    metadata_summary=metadata_summary,
                    pcd_count=len(pcd_files_data),
                )
            )
        return summaries

    def _query_results_by_node(
        self, node_id: str, limit: int, offset: int
    ) -> List[ApplicationResultModel]:
        with self._get_session() as session:
            rows = (
                session.query(ApplicationResultModel)
                .filter(ApplicationResultModel.node_id == node_id)
                .order_by(ApplicationResultModel.timestamp.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            # Detach from session to avoid lazy-load issues outside context
            session.expunge_all()
            return rows

    async def get_result_detail(
        self, node_id: str, result_id: str
    ) -> Optional[ResultDetail]:
        """Return full result detail, or None if not found."""
        row = await asyncio.to_thread(self._query_result_detail, node_id, result_id)
        if row is None:
            return None
        metadata: Dict[str, Any] = (
            json.loads(row.metadata_json) if row.metadata_json else {}
        )
        pcd_entries: List[Dict[str, str]] = (
            json.loads(row.pcd_files_json) if row.pcd_files_json else []
        )
        pcd_files = [
            PcdFileEntry(
                label=entry["label"],
                url=self._pcd_url(node_id, result_id, entry["label"]),
            )
            for entry in pcd_entries
        ]
        return ResultDetail(
            result_id=row.result_id,
            node_id=row.node_id,
            timestamp=row.timestamp,
            status=_cast(Any, row.status),
            metadata=metadata,
            pcd_files=pcd_files,
        )

    def _query_result_detail(
        self, node_id: str, result_id: str
    ) -> Optional[ApplicationResultModel]:
        with self._get_session() as session:
            row = (
                session.query(ApplicationResultModel)
                .filter(
                    ApplicationResultModel.node_id == node_id,
                    ApplicationResultModel.result_id == result_id,
                )
                .first()
            )
            if row is not None:
                session.expunge(row)
            return row

    async def delete_results_by_node(self, node_id: str) -> int:
        """Delete all results for a node. DB first, then disk.

        Called by the orchestrator on node delete.

        Returns:
            Number of DB records deleted.
        """
        count = await asyncio.to_thread(self._delete_node_db, node_id)
        node_dir = Path(_RESULTS_BASE) / node_id
        if node_dir.exists():
            try:
                shutil.rmtree(node_dir)
                logger.info("ResultsStorageService: removed directory %s", node_dir)
            except Exception as exc:
                logger.error(
                    "ResultsStorageService: failed to remove %s: %s", node_dir, exc
                )
        return count

    def _delete_node_db(self, node_id: str) -> int:
        with self._get_session() as session:
            deleted = (
                session.query(ApplicationResultModel)
                .filter(ApplicationResultModel.node_id == node_id)
                .delete(synchronize_session=False)
            )
            session.commit()
            return deleted

    async def delete_result(self, node_id: str, result_id: str) -> bool:
        """Delete a single result record and its PCD files.

        Returns:
            True if deleted, False if not found.
        """
        deleted_count = await asyncio.to_thread(
            self._delete_result_db, node_id, result_id
        )
        if deleted_count == 0:
            return False
        result_dir = self._result_dir(node_id, result_id)
        if result_dir.exists():
            try:
                shutil.rmtree(result_dir)
            except Exception as exc:
                logger.error(
                    "ResultsStorageService: failed to remove result dir %s: %s",
                    result_dir,
                    exc,
                )
        return True

    def _delete_result_db(self, node_id: str, result_id: str) -> int:
        with self._get_session() as session:
            deleted = (
                session.query(ApplicationResultModel)
                .filter(
                    ApplicationResultModel.node_id == node_id,
                    ApplicationResultModel.result_id == result_id,
                )
                .delete(synchronize_session=False)
            )
            session.commit()
            return deleted

    # -------------------------------------------------------------------------
    # Startup orphan sweep
    # -------------------------------------------------------------------------

    async def sweep_orphans(self) -> None:
        """Delete disk directories that have no corresponding DB record.

        Called once at application startup after DB migration.
        """
        await asyncio.to_thread(self._sweep_orphans_sync)

    def _sweep_orphans_sync(self) -> None:
        base = Path(_RESULTS_BASE)
        if not base.exists():
            return
        with self._get_session() as session:
            for node_dir in base.iterdir():
                if not node_dir.is_dir():
                    continue
                for result_dir in node_dir.iterdir():
                    if not result_dir.is_dir():
                        continue
                    result_id = result_dir.name
                    node_id = node_dir.name
                    exists = (
                        session.query(ApplicationResultModel.result_id)
                        .filter(
                            ApplicationResultModel.node_id == node_id,
                            ApplicationResultModel.result_id == result_id,
                        )
                        .first()
                    )
                    if exists is None:
                        logger.warning(
                            "ResultsStorageService: orphan directory %s — deleting",
                            result_dir,
                        )
                        shutil.rmtree(result_dir, ignore_errors=True)
