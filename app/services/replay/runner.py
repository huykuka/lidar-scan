"""Replay service: run a recording through an isolated snapshot of the DAG.

A run builds a *separate* ``NodeManager`` (``isolated=True``) containing only the
sub-graph reachable downstream of one PlaybackNode.  The live DAG is never touched:

* no websocket topics, no recorder interception, no shape broadcast
* throttling is disabled (it is wall-clock based and would drop frames in fast mode)
* ``ResultStorageNode`` results are captured in memory, not written to the DB/disk
* the PlaybackNode runs in fast mode (no inter-frame sleep, downstream awaited per frame)
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import shutil
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.core.logging import get_logger
from app.repositories import EdgeRepository, NodeRepository, RecordingRepository
from app.repositories.replay_orm import (
    ReplayRunRepository,
    ReplaySweepRepository,
    ReplayTargetRepository,
)
from app.services.nodes.managers.routing import DataRouter

from .manager import ReplayNodeManager
from .capture import CapturingResultsService, OutputCapture, summarize
from .clouds import CloudCapture, read_cloud
from .scoring import score_run
from .values import same_value

logger = get_logger(__name__)

REPLAY_DIR = Path("data/replays")
PLAYBACK_TYPE = "playback"
MAX_SWEEP_RUNS = 30
_PROGRESS_INTERVAL_S = 0.5


class ReplayError(Exception):
    """Raised for invalid replay requests (mapped to HTTP 4xx by the API layer)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class ReplayDataRouter(DataRouter):
    """DataRouter without side effects: captures outputs, then forwards downstream."""

    def __init__(self, manager_ref: Any, capture: OutputCapture, clouds: Optional[CloudCapture] = None):
        super().__init__(manager_ref)
        self._capture = capture
        self._clouds = clouds

    async def forward_data(self, source_id: str, payload: Any, active_port: Optional[str] = None):
        self._capture.record_output(source_id, payload)
        if self._clouds is not None:
            self._clouds.record(source_id, payload)
        await self._forward_to_downstream_nodes(source_id, payload, active_port=active_port)

    async def _send_to_target_node(self, source_id: str, target_id: str, payload: Dict[str, Any]):
        target_node = self.manager.nodes.get(target_id)
        if not target_node or not hasattr(target_node, "on_input"):
            return
        try:
            await target_node.on_input({**payload})
        except Exception as exc:  # keep replaying; the failure is part of the run result
            self._capture.record_error(source_id, target_id, exc)
            logger.error("[replay] node %s failed on input from %s: %s", target_id, source_id, exc)

    async def publish_shapes(self) -> None:  # no websocket broadcast in replay
        return None


def reachable_subgraph(
    nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], root_id: str
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Enabled nodes reachable from ``root_id`` (inclusive) and the edges between them."""
    by_id = {n["id"]: n for n in nodes if n.get("enabled", True)}
    if root_id not in by_id:
        raise ReplayError(f"Playback node '{root_id}' not found or disabled", 404)

    adjacency: Dict[str, List[str]] = {}
    for edge in edges:
        src, dst = edge.get("source_node"), edge.get("target_node")
        if src and dst:
            adjacency.setdefault(src, []).append(dst)

    seen: Set[str] = {root_id}
    stack = [root_id]
    while stack:
        for nxt in adjacency.get(stack.pop(), []):
            if nxt in by_id and nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)

    sub_nodes = [copy.deepcopy(by_id[nid]) for nid in seen]
    sub_edges = [
        copy.deepcopy(e) for e in edges
        if e.get("source_node") in seen and e.get("target_node") in seen
    ]
    return sub_nodes, sub_edges


def apply_overrides(
    nodes: List[Dict[str, Any]],
    overrides: Dict[str, Dict[str, Any]],
    playback_node_id: str,
    recording_id: str,
) -> None:
    """Merge per-node config overrides in place and pin the playback source."""
    ids = {n["id"] for n in nodes}
    unknown = set(overrides) - ids
    if unknown:
        raise ReplayError(
            f"Overrides reference nodes outside the replayed sub-graph: {sorted(unknown)}"
        )
    for node in nodes:
        cfg = dict(node.get("config") or {})
        cfg.update(overrides.get(node["id"], {}))
        if node["id"] == playback_node_id:
            cfg["recording_id"] = recording_id
            cfg["loopable"] = False
            cfg["throttle_ms"] = 0
        node["config"] = cfg


def default_capture_nodes(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[str]:
    """The pipeline's final nodes (no outgoing edge) plus the nodes feeding them.

    Terminal sinks (e.g. Result Storage) never forward a cloud, so their direct parents are
    the clouds worth looking at.
    """
    has_out = {e.get("source_node") for e in edges}
    leaves = [n["id"] for n in nodes if n["id"] not in has_out]
    parents = [e["source_node"] for e in edges if e.get("target_node") in leaves]
    ordered = list(dict.fromkeys([*parents, *leaves]))
    return [nid for nid in ordered if nid in {n["id"] for n in nodes}]


def resolve_capture_nodes(
    requested: Optional[List[str]], nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]
) -> List[str]:
    """Validate the requested capture nodes (default: final nodes and their parents)."""
    if requested is None:
        return default_capture_nodes(nodes, edges)
    ids = {n["id"] for n in nodes}
    unknown = [n for n in requested if n not in ids]
    if unknown:
        raise ReplayError(
            f"capture_nodes reference nodes outside the replayed sub-graph: {sorted(unknown)}"
        )
    return list(dict.fromkeys(requested))


def config_hash(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> str:
    """Stable hash of the effective (post-override) sub-graph configuration."""
    canon = {
        "nodes": sorted(
            ({"id": n["id"], "type": n.get("type"), "config": n.get("config"), "pose": n.get("pose")}
             for n in nodes),
            key=lambda n: n["id"],
        ),
        "edges": sorted(
            ((e.get("source_node"), e.get("source_port"), e.get("target_node"), e.get("target_port"))
             for e in edges),
            key=str,
        ),
    }
    return hashlib.sha256(json.dumps(canon, sort_keys=True, default=str).encode()).hexdigest()[:16]


def outputs_path(run_id: str) -> Path:
    return REPLAY_DIR / f"{run_id}.json"


def run_dir(run_id: str) -> Path:
    return REPLAY_DIR / run_id


class ReplayService:
    """Creates and executes replay runs (one at a time)."""

    def __init__(self) -> None:
        self._repo = ReplayRunRepository()
        self._sweeps = ReplaySweepRepository()
        self._targets = ReplayTargetRepository()
        # One run at a time. A semaphore binds to the loop that first contends for it, so it is
        # (re)created lazily per running loop instead of once here.
        self._gate: Optional[asyncio.Semaphore] = None
        self._gate_loop: Optional[asyncio.AbstractEventLoop] = None
        self._tasks: Dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------ API

    def create_run(
        self,
        *,
        recording_id: str,
        playback_node_id: str,
        overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        label: str = "",
        capture_nodes: Optional[List[str]] = None,
        sweep_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate the request, persist a queued run and start it in the background."""
        from app.db.session import SessionLocal, get_engine

        get_engine()
        with SessionLocal() as db:
            recording = RecordingRepository(db).get_by_id(recording_id)
        if recording is None:
            raise ReplayError(f"Recording '{recording_id}' not found", 404)
        if recording.get("status", "ready") != "ready" or int(recording.get("frame_count", 0)) == 0:
            raise ReplayError(f"Recording '{recording_id}' is not ready or has no frames")

        all_nodes = NodeRepository().list()
        all_edges = EdgeRepository().list()
        playback = next((n for n in all_nodes if n["id"] == playback_node_id), None)
        if playback is None:
            raise ReplayError(f"Node '{playback_node_id}' not found", 404)
        if playback.get("type") != PLAYBACK_TYPE:
            raise ReplayError(f"Node '{playback_node_id}' is not a playback node")

        nodes, edges = reachable_subgraph(all_nodes, all_edges, playback_node_id)
        apply_overrides(nodes, overrides or {}, playback_node_id, recording_id)
        capture_ids = resolve_capture_nodes(capture_nodes, nodes, edges)

        run_id = uuid.uuid4().hex
        row = self._repo.create({
            "id": run_id,
            "label": label or f"run-{run_id[:6]}",
            "recording_id": recording_id,
            "playback_node_id": playback_node_id,
            "status": "queued",
            "frames_total": int(recording["frame_count"]),
            "frames_processed": 0,
            "config_hash": config_hash(nodes, edges),
            "overrides": overrides or {},
            "config_snapshot": {"nodes": nodes, "edges": edges, "capture_nodes": capture_ids},
            "capture_nodes": capture_ids,
            "sweep_id": sweep_id,
        })
        self._tasks[run_id] = asyncio.create_task(
            self._execute(run_id, nodes, edges, playback_node_id, capture_ids),
            name=f"replay-{run_id}",
        )
        return row

    def _run_gate(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if self._gate is None or self._gate_loop is not loop:
            self._gate, self._gate_loop = asyncio.Semaphore(1), loop
        return self._gate

    async def cancel(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        # A task cancelled before its first step never ran its own cleanup.
        run = self._repo.get(run_id)
        if run and run["status"] in ("queued", "running"):
            self._repo.update(run_id, {
                "status": "failed", "error": "Cancelled",
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
        return True

    # ----------------------------------------------------------------- sweeps

    def create_sweep(
        self,
        *,
        recording_id: str,
        playback_node_id: str,
        node_id: str,
        parameter: str,
        values: List[Any],
        label: str = "",
        capture_nodes: Optional[List[str]] = None,
        include_current: bool = True,
    ) -> Dict[str, Any]:
        """Queue one run per value of ``node_id.parameter`` (plus the current value as baseline)."""
        parameter = (parameter or "").strip()
        if not parameter:
            raise ReplayError("A parameter name is required")
        unique: List[Any] = []
        for v in values:
            if not any(same_value(v, u) for u in unique):
                unique.append(v)
        node = NodeRepository().get_by_id(node_id)
        if node is None:
            raise ReplayError(f"Node '{node_id}' not found", 404)
        current = (node.get("config") or {}).get(parameter)
        add_baseline = include_current and current is not None and not any(same_value(current, u) for u in unique)
        if not unique:
            raise ReplayError("At least one value is required")
        if len(unique) + int(add_baseline) > MAX_SWEEP_RUNS:
            raise ReplayError(f"A sweep is limited to {MAX_SWEEP_RUNS} runs")

        sweep = self._sweeps.create({
            "id": uuid.uuid4().hex,
            "label": label or f"{parameter} sweep",
            "recording_id": recording_id,
            "playback_node_id": playback_node_id,
            "node_id": node_id,
            "parameter": parameter,
            "values": unique,
        })
        created: List[str] = []
        try:
            plan: List[tuple[str, Optional[Any]]] = []
            if add_baseline:
                plan.append((f"{parameter}={current} (current)", None))
            plan += [(f"{parameter}={v}", v) for v in unique]
            for run_label, value in plan:
                run = self.create_run(
                    recording_id=recording_id,
                    playback_node_id=playback_node_id,
                    overrides={} if value is None else {node_id: {parameter: value}},
                    label=run_label,
                    capture_nodes=capture_nodes,
                    sweep_id=sweep["id"],
                )
                created.append(run["id"])
        except Exception:
            # All-or-nothing: don't leave a half-queued sweep behind.
            for run_id in created:
                task = self._tasks.get(run_id)
                if task is not None:
                    task.cancel()
                self.delete_run(run_id)
            self._sweeps.delete(sweep["id"])
            raise
        return sweep

    async def cancel_sweep(self, sweep_id: str) -> int:
        """Cancel every queued/running run of a sweep. Returns how many were cancelled."""
        cancelled = 0
        for run in self._repo.list(sweep_id=sweep_id):
            if run["status"] in ("queued", "running") and await self.cancel(run["id"]):
                cancelled += 1
        return cancelled

    def delete_sweep(self, sweep_id: str) -> bool:
        for run in self._repo.list(sweep_id=sweep_id):
            self.delete_run(run["id"])
        return self._sweeps.delete(sweep_id)

    # ---------------------------------------------------------------- scoring

    def targets_for(self, recording_id: str) -> List[Dict[str, Any]]:
        return self._targets.list(recording_id)

    def with_scores(self, run: Dict[str, Any], targets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Attach ``scores`` (vs the recording's ground truth) to a run dict."""
        if targets is None:
            targets = self.targets_for(run["recording_id"])
        scored = score_run(run.get("summary") or {}, targets) if run["status"] == "completed" else {
            "overall": None, "targets": [],
        }
        return {**run, "scores": scored}

    def get_outputs(self, run_id: str) -> Optional[Dict[str, Any]]:
        path = outputs_path(run_id)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def delete_run(self, run_id: str) -> bool:
        outputs_path(run_id).unlink(missing_ok=True)
        shutil.rmtree(run_dir(run_id), ignore_errors=True)
        return self._repo.delete(run_id)

    def get_cloud(self, run_id: str, node_id: str, frame: int):
        return read_cloud(run_dir(run_id), node_id, frame)

    def recover_interrupted(self) -> int:
        return self._repo.mark_unfinished_failed()

    # ------------------------------------------------------------- execution

    async def _execute(
        self,
        run_id: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        playback_node_id: str,
        capture_ids: List[str],
    ) -> None:
        started = time.monotonic()

        def _finish(updates: Dict[str, Any]) -> None:
            self._repo.update(run_id, {
                **updates,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": time.monotonic() - started,
            })

        try:
            # Cancellation can arrive while queued (waiting for the gate) or while running.
            async with self._run_gate():
                started = time.monotonic()
                self._repo.update(run_id, {"status": "running"})
                capture, frames_done, clouds_meta = await self._replay(
                    run_id, nodes, edges, playback_node_id, capture_ids
                )
                data = capture.to_dict()
                REPLAY_DIR.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(
                    outputs_path(run_id).write_text, json.dumps({"run_id": run_id, **data})
                )
                _finish({
                    "status": "completed",
                    "frames_processed": frames_done,
                    "summary": {**summarize(data), "clouds": clouds_meta},
                })
        except asyncio.CancelledError:
            shutil.rmtree(run_dir(run_id), ignore_errors=True)
            _finish({"status": "failed", "error": "Cancelled"})
            raise
        except Exception as exc:
            logger.error("[replay] run %s failed: %s", run_id, exc, exc_info=True)
            shutil.rmtree(run_dir(run_id), ignore_errors=True)
            _finish({"status": "failed", "error": str(exc)})
        finally:
            self._tasks.pop(run_id, None)

    async def _replay(
        self,
        run_id: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        playback_node_id: str,
        capture_ids: List[str],
    ) -> tuple[OutputCapture, int, Dict[str, Any]]:
        manager = ReplayNodeManager()
        node_meta = {n["id"]: {"name": n.get("name", n["id"]), "type": n.get("type", "")} for n in nodes}
        # frame getter closes over ``manager`` — resolved lazily once the playback node exists
        capture = OutputCapture(
            lambda: max(getattr(manager.nodes.get(playback_node_id), "current_frame", 0) - 1, 0),
            node_meta,
        )
        clouds = CloudCapture(
            run_dir(run_id), capture_ids,
            lambda: max(getattr(manager.nodes.get(playback_node_id), "current_frame", 0) - 1, 0),
        )
        manager._data_router = ReplayDataRouter(manager, capture, clouds)

        manager._config_loader.initialize_nodes(nodes, edges)
        missing = [n["id"] for n in nodes if n["id"] not in manager.nodes]
        if missing:
            raise ReplayError(
                "Could not build nodes for replay: "
                + ", ".join(f"{node_meta[i]['name']} ({i[:8]})" for i in missing)
                + " — see server log for details"
            )
        manager.downstream_map = manager._config_loader.build_downstream_map(edges)

        # Wall-clock throttling would drop frames in fast mode.
        manager._throttle_config = {nid: 0.0 for nid in manager.nodes}

        results_service = CapturingResultsService(capture)
        for node in manager.nodes.values():
            if hasattr(node, "_results_service"):
                node._results_service = results_service

        playback = manager.nodes[playback_node_id]
        playback._fast_mode = True

        manager.is_running = True
        progress_task: Optional[asyncio.Task] = None
        try:
            await manager._lifecycle_manager.start_all_nodes()
            progress_task = asyncio.create_task(self._report_progress(run_id, playback))
            await playback.wait_finished()
            if playback.status == "error":
                raise ReplayError(playback.error_message or "Playback failed", 500)
            return capture, int(playback.total_frames), clouds.finalize(
                {nid: meta["name"] for nid, meta in node_meta.items()}
            )
        except BaseException:
            clouds.discard()
            raise
        finally:
            if progress_task is not None:
                progress_task.cancel()
            manager.is_running = False
            try:
                await manager._lifecycle_manager.stop_all_nodes()
            except Exception as exc:
                logger.warning("[replay] error stopping nodes for run %s: %s", run_id, exc)
            try:
                manager.data_queue.close()
                manager.data_queue.cancel_join_thread()
            except Exception:
                pass

    async def _report_progress(self, run_id: str, playback: Any) -> None:
        last = -1
        while True:
            await asyncio.sleep(_PROGRESS_INTERVAL_S)
            current = int(playback.current_frame)
            if current != last:
                last = current
                await asyncio.to_thread(self._repo.update, run_id, {"frames_processed": current})


_service: Optional[ReplayService] = None


def get_replay_service() -> ReplayService:
    global _service
    if _service is None:
        _service = ReplayService()
    return _service
