"""Repository for replay run persistence using SQLAlchemy ORM."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.db.models import ReplayRunModel, ReplaySweepModel, ReplayTargetModel
from app.db.session import SessionLocal, get_engine


class ReplayRunRepository:
    """CRUD for ``replay_runs``.  Opens a short-lived session per call."""

    def _session(self):
        get_engine()
        return SessionLocal()

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(data)
        for key, col in (
            ("overrides", "overrides_json"),
            ("config_snapshot", "config_snapshot_json"),
            ("summary", "summary_json"),
            ("capture_nodes", "capture_nodes_json"),
        ):
            if key in payload:
                payload[col] = json.dumps(payload.pop(key), default=str)
        with self._session() as db:
            row = ReplayRunModel(**payload)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.to_dict()

    def update(self, run_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = dict(updates)
        if "summary" in payload:
            payload["summary_json"] = json.dumps(payload.pop("summary"), default=str)
        with self._session() as db:
            row = db.query(ReplayRunModel).filter(ReplayRunModel.id == run_id).first()
            if row is None:
                return None
            for key, value in payload.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            db.commit()
            db.refresh(row)
            return row.to_dict()

    def get(self, run_id: str, include_snapshot: bool = False) -> Optional[Dict[str, Any]]:
        with self._session() as db:
            row = db.query(ReplayRunModel).filter(ReplayRunModel.id == run_id).first()
            return row.to_dict(include_snapshot=include_snapshot) if row else None

    def list(
        self,
        recording_id: Optional[str] = None,
        sweep_id: Optional[str] = None,
        standalone_only: bool = False,
    ) -> List[Dict[str, Any]]:
        with self._session() as db:
            query = db.query(ReplayRunModel)
            if recording_id:
                query = query.filter(ReplayRunModel.recording_id == recording_id)
            if sweep_id:
                query = query.filter(ReplayRunModel.sweep_id == sweep_id)
            elif standalone_only:
                query = query.filter(ReplayRunModel.sweep_id.is_(None))
            return [r.to_dict() for r in query.order_by(ReplayRunModel.created_at.desc()).all()]

    def delete(self, run_id: str) -> bool:
        with self._session() as db:
            row = db.query(ReplayRunModel).filter(ReplayRunModel.id == run_id).first()
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    def mark_unfinished_failed(self) -> int:
        """Called at startup: runs left queued/running by a crash can never finish."""
        with self._session() as db:
            rows = db.query(ReplayRunModel).filter(
                ReplayRunModel.status.in_(("queued", "running"))
            ).all()
            for row in rows:
                row.status = "failed"
                row.error = "Interrupted by server restart"
            db.commit()
            return len(rows)


class ReplaySweepRepository:
    """CRUD for ``replay_sweeps``."""

    def _session(self):
        get_engine()
        return SessionLocal()

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(data)
        if "values" in payload:
            payload["values_json"] = json.dumps(payload.pop("values"), default=str)
        with self._session() as db:
            row = ReplaySweepModel(**payload)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.to_dict()

    def get(self, sweep_id: str) -> Optional[Dict[str, Any]]:
        with self._session() as db:
            row = db.query(ReplaySweepModel).filter(ReplaySweepModel.id == sweep_id).first()
            return row.to_dict() if row else None

    def list(self, recording_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._session() as db:
            query = db.query(ReplaySweepModel)
            if recording_id:
                query = query.filter(ReplaySweepModel.recording_id == recording_id)
            return [r.to_dict() for r in query.order_by(ReplaySweepModel.created_at.desc()).all()]

    def delete(self, sweep_id: str) -> bool:
        with self._session() as db:
            row = db.query(ReplaySweepModel).filter(ReplaySweepModel.id == sweep_id).first()
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True


class ReplayTargetRepository:
    """CRUD for ``replay_targets`` (ground truth values)."""

    def _session(self):
        get_engine()
        return SessionLocal()

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._session() as db:
            row = ReplayTargetModel(**data)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.to_dict()

    def list(self, recording_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._session() as db:
            query = db.query(ReplayTargetModel)
            if recording_id:
                query = query.filter(ReplayTargetModel.recording_id == recording_id)
            return [r.to_dict() for r in query.order_by(ReplayTargetModel.created_at.asc()).all()]

    def delete(self, target_id: str) -> bool:
        with self._session() as db:
            row = db.query(ReplayTargetModel).filter(ReplayTargetModel.id == target_id).first()
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True
