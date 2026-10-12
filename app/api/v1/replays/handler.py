"""Replays router: offline replay of recordings through the DAG + run comparison."""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.v1.auth.dependencies import _make_role_guard, roles_required
from app.repositories.replay_orm import ReplayRunRepository, ReplaySweepRepository, ReplayTargetRepository
from app.services.replay import ReplayError, get_replay_service
from app.services.replay.apply import apply_to_pipeline, preview_apply
from app.services.replay.scoring import rank_key
from app.services.replay.clouds import common_cloud_nodes, diff_clouds, pack_cloud_diff
from app.services.replay.compare import compare_runs

from .dto import (
    ApplyResponse,
    CreateReplayRequest,
    CreateSweepRequest,
    CreateTargetRequest,
    ListReplayRunsResponse,
    ListSweepsResponse,
    ListTargetsResponse,
    ReplayRunResponse,
    SweepDetailResponse,
    SweepResponse,
    TargetResponse,
)

# Replays are service-only.
router = APIRouter(tags=["Replays"], dependencies=[Depends(_make_role_guard("service"))])


def _get_run_or_404(run_id: str, include_snapshot: bool = False) -> dict:
    run = ReplayRunRepository().get(run_id, include_snapshot=include_snapshot)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Replay run {run_id} not found")
    return run


def _scored(run: dict) -> dict:
    return get_replay_service().with_scores(run)


def _sweep_progress(sweep: dict) -> dict:
    runs = ReplayRunRepository().list(sweep_id=sweep["id"])
    count = lambda *states: sum(1 for r in runs if r["status"] in states)  # noqa: E731
    return {
        **sweep,
        "progress": {
            "total": len(runs),
            "completed": count("completed"),
            "failed": count("failed"),
            "active": count("queued", "running"),
        },
    }


def _with_sweep_value(run: dict, sweep: dict) -> dict:
    """Add the swept parameter's value for this run (the baseline run has no override, so its
    value comes from the pipeline configuration it ran with)."""
    override = (run.get("overrides") or {}).get(sweep["node_id"], {})
    if sweep["parameter"] in override:
        return {**run, "x_value": override[sweep["parameter"]], "is_baseline": False}
    full = ReplayRunRepository().get(run["id"], include_snapshot=True) or {}
    node = next(
        (n for n in (full.get("config_snapshot") or {}).get("nodes", []) if n["id"] == sweep["node_id"]),
        None,
    )
    value = ((node or {}).get("config") or {}).get(sweep["parameter"])
    return {**run, "x_value": value, "is_baseline": True}


def _get_sweep_or_404(sweep_id: str) -> dict:
    sweep = ReplaySweepRepository().get(sweep_id)
    if sweep is None:
        raise HTTPException(status_code=404, detail=f"Sweep {sweep_id} not found")
    return sweep


def _load_outputs_or_409(run: dict) -> dict:
    if run["status"] != "completed":
        raise HTTPException(
            status_code=409, detail=f"Replay run {run['id']} is {run['status']}, not completed"
        )
    outputs = get_replay_service().get_outputs(run["id"])
    if outputs is None:
        raise HTTPException(status_code=404, detail=f"Outputs for run {run['id']} are missing")
    return outputs


@router.post(
    "/replays",
    response_model=ReplayRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start Replay",
    description=(
        "Replay a recording as fast as possible through the sub-graph downstream of a Playback "
        "node, in an isolated copy of the DAG (live pipeline, websockets and stored results are "
        "not affected). Returns immediately; poll GET /replays/{id} for progress."
    ),
    responses={
        400: {"description": "Invalid request"},
        404: {"description": "Recording or node not found"},
    },
)
async def start_replay(request: CreateReplayRequest):
    try:
        # Runs on the event loop thread: it only does small DB reads and schedules the run task.
        return get_replay_service().create_run(
            recording_id=request.recording_id,
            playback_node_id=request.playback_node_id,
            overrides=request.overrides,
            label=request.label,
            capture_nodes=request.capture_nodes,
        )
    except ReplayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get(
    "/replays",
    response_model=ListReplayRunsResponse,
    summary="List Replay Runs",
    description="Stand-alone runs (runs that belong to a sweep are listed under the sweep).",
)
async def list_replays(
    recording_id: Optional[str] = Query(default=None),
    include_sweep_runs: bool = Query(default=False),
):
    def _load() -> list:
        runs = ReplayRunRepository().list(recording_id, standalone_only=not include_sweep_runs)
        targets_by_rec: dict = {}
        out = []
        for run in runs:
            targets = targets_by_rec.setdefault(
                run["recording_id"], get_replay_service().targets_for(run["recording_id"])
            )
            out.append(get_replay_service().with_scores(run, targets))
        return out

    runs = await asyncio.to_thread(_load)
    return {"runs": runs, "total": len(runs)}


# ── Parameter sweeps ────────────────────────────────────────────────────────────
# NOTE: static paths (/replays/sweeps, /replays/targets, /replays/compare) are declared
# before /replays/{run_id} so they are not captured as run ids.

@router.post(
    "/replays/sweeps",
    response_model=SweepResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start Parameter Sweep",
    description=(
        "Queue one replay run per value of a node parameter (plus the current value as a "
        "baseline). Runs execute one at a time; poll GET /replays/sweeps/{id}."
    ),
    responses={400: {"description": "Invalid request"}, 404: {"description": "Recording or node not found"}},
)
async def start_sweep(request: CreateSweepRequest):
    try:
        sweep = get_replay_service().create_sweep(
            recording_id=request.recording_id,
            playback_node_id=request.playback_node_id,
            node_id=request.node_id,
            parameter=request.parameter,
            values=request.values,
            label=request.label,
            capture_nodes=request.capture_nodes,
            include_current=request.include_current,
        )
    except ReplayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return await asyncio.to_thread(_sweep_progress, sweep)


@router.get("/replays/sweeps", response_model=ListSweepsResponse, summary="List Sweeps")
async def list_sweeps(recording_id: Optional[str] = Query(default=None)):
    def _load() -> list:
        return [_sweep_progress(s) for s in ReplaySweepRepository().list(recording_id)]

    sweeps = await asyncio.to_thread(_load)
    return {"sweeps": sweeps, "total": len(sweeps)}


@router.get(
    "/replays/sweeps/{sweep_id}",
    response_model=SweepDetailResponse,
    summary="Get Sweep",
    responses={404: {"description": "Sweep not found"}},
)
async def get_sweep(sweep_id: str):
    def _load() -> dict:
        sweep = _get_sweep_or_404(sweep_id)
        service = get_replay_service()
        targets = service.targets_for(sweep["recording_id"])
        runs = [service.with_scores(r, targets) for r in ReplayRunRepository().list(sweep_id=sweep_id)]
        runs.sort(key=lambda r: r["created_at"])
        runs = [_with_sweep_value(r, sweep) for r in runs]
        scored = [r for r in runs if r["status"] == "completed" and r["scores"]["targets"]]
        best = min(scored, key=lambda r: rank_key(r["scores"]), default=None)
        return {
            "sweep": _sweep_progress(sweep),
            "runs": runs,
            "targets": targets,
            "best_run_id": best["id"] if best and rank_key(best["scores"]) != float("inf") else None,
        }

    return await asyncio.to_thread(_load)


@router.post(
    "/replays/sweeps/{sweep_id}/cancel",
    summary="Cancel Sweep",
    responses={404: {"description": "Sweep not found"}},
)
async def cancel_sweep(sweep_id: str):
    await asyncio.to_thread(_get_sweep_or_404, sweep_id)
    return {"cancelled": await get_replay_service().cancel_sweep(sweep_id)}


@router.delete(
    "/replays/sweeps/{sweep_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Sweep",
    responses={404: {"description": "Sweep not found"}, 409: {"description": "Sweep is still running"}},
)
async def delete_sweep(sweep_id: str):
    sweep = await asyncio.to_thread(_get_sweep_or_404, sweep_id)
    if (await asyncio.to_thread(_sweep_progress, sweep))["progress"]["active"]:
        raise HTTPException(status_code=409, detail="Cancel the sweep before deleting it")
    await asyncio.to_thread(get_replay_service().delete_sweep, sweep_id)


# ── Ground truth ────────────────────────────────────────────────────────────────

@router.get("/replays/targets", response_model=ListTargetsResponse, summary="List Ground Truth Targets")
async def list_targets(recording_id: Optional[str] = Query(default=None)):
    targets = await asyncio.to_thread(ReplayTargetRepository().list, recording_id)
    return {"targets": targets}


@router.post(
    "/replays/targets",
    response_model=TargetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Ground Truth Target",
    responses={404: {"description": "Recording not found"}},
)
async def create_target(request: CreateTargetRequest):
    import uuid

    from app.db.session import SessionLocal, get_engine
    from app.repositories import RecordingRepository

    def _create() -> dict:
        get_engine()
        with SessionLocal() as db:
            if RecordingRepository(db).get_by_id(request.recording_id) is None:
                raise HTTPException(status_code=404, detail=f"Recording {request.recording_id} not found")
        return ReplayTargetRepository().create({"id": uuid.uuid4().hex, **request.model_dump()})

    return await asyncio.to_thread(_create)


@router.delete(
    "/replays/targets/{target_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Ground Truth Target",
    responses={404: {"description": "Target not found"}},
)
async def delete_target(target_id: str):
    if not await asyncio.to_thread(ReplayTargetRepository().delete, target_id):
        raise HTTPException(status_code=404, detail=f"Target {target_id} not found")


# NOTE: declared before /replays/{run_id} so "compare" is not captured as a run id.
@router.get(
    "/replays/compare",
    summary="Compare Two Replay Runs",
    description="Diff the captured outputs of two completed runs (a = baseline, b = candidate).",
    responses={404: {"description": "Run not found"}, 409: {"description": "Run not completed"}},
)
async def compare_replays(a: str = Query(...), b: str = Query(...)):
    run_a, run_b = _get_run_or_404(a), _get_run_or_404(b)

    def _compare() -> dict:
        return compare_runs(_load_outputs_or_409(run_a), _load_outputs_or_409(run_b))

    result = await asyncio.to_thread(_compare)
    info_keys = (
        "id", "label", "recording_id", "config_hash", "overrides",
        "duration_seconds", "frames_processed", "frames_total",
    )
    result["run_a_info"] = {k: run_a[k] for k in info_keys}
    result["run_b_info"] = {k: run_b[k] for k in info_keys}
    result["same_recording"] = run_a["recording_id"] == run_b["recording_id"]
    result["cloud_nodes"] = common_cloud_nodes(run_a["summary"], run_b["summary"])
    service = get_replay_service()
    result["scores_a"] = service.with_scores(run_a)["scores"]
    result["scores_b"] = service.with_scores(run_b)["scores"]
    return result


@router.get(
    "/replays/compare/cloud",
    summary="Visual Diff of One Frame",
    description=(
        "Point clouds of one node/frame from two runs, each point flagged when the other run "
        "has no point within `tol` (same unit as the cloud, normally metres). Binary response: "
        "32-byte header (u32 nA, nB, onlyA, onlyB, f32 meanDistA, meanDistB), then A xyz f32, "
        "A flags u8, B xyz f32, B flags u8 (each block padded to 4 bytes)."
    ),
    response_class=Response,
    responses={
        200: {"content": {"application/octet-stream": {}}},
        404: {"description": "Run, node or frame not captured"},
    },
)
async def compare_replay_cloud(
    a: str = Query(...),
    b: str = Query(...),
    node_id: str = Query(...),
    frame: int = Query(..., ge=0),
    tol: float = Query(default=0.05, gt=0, le=10),
):
    _get_run_or_404(a)
    _get_run_or_404(b)
    service = get_replay_service()

    def _build() -> Optional[bytes]:
        cloud_a = service.get_cloud(a, node_id, frame)
        cloud_b = service.get_cloud(b, node_id, frame)
        if cloud_a is None or cloud_b is None:
            return None
        return pack_cloud_diff(cloud_a, cloud_b, diff_clouds(cloud_a, cloud_b, tol))

    payload = await asyncio.to_thread(_build)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"No captured point cloud for node {node_id} at frame {frame} in both runs",
        )
    return Response(content=payload, media_type="application/octet-stream")


@router.get(
    "/replays/{run_id}",
    response_model=ReplayRunResponse,
    summary="Get Replay Run",
    responses={404: {"description": "Run not found"}},
)
async def get_replay(run_id: str, include_snapshot: bool = Query(default=False)):
    run = await asyncio.to_thread(_get_run_or_404, run_id, include_snapshot)
    return await asyncio.to_thread(_scored, run)


@router.get(
    "/replays/{run_id}/apply-preview",
    summary="Preview Applying a Run to the Pipeline",
    description="What the run's parameter overrides would change in the live pipeline (read-only).",
    responses={404: {"description": "Run not found"}},
)
async def preview_apply_replay(run_id: str):
    try:
        return await asyncio.to_thread(preview_apply, run_id)
    except ReplayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post(
    "/replays/{run_id}/apply",
    response_model=ApplyResponse,
    summary="Apply a Run's Parameters to the Live Pipeline",
    description=(
        "Writes the run's parameter overrides into the saved pipeline and reloads the affected "
        "nodes, exactly like saving them in Settings. Requires the admin role."
    ),
    responses={
        404: {"description": "Run not found"},
        409: {"description": "Nothing to apply, nodes missing, or the pipeline is reloading"},
    },
)
@roles_required("admin")
async def apply_replay(run_id: str):
    try:
        return await apply_to_pipeline(run_id)
    except ReplayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get(
    "/replays/{run_id}/outputs",
    summary="Get Replay Outputs",
    description="Per-node, per-frame captured outputs and saved results of a completed run.",
    responses={404: {"description": "Run not found"}, 409: {"description": "Run not completed"}},
)
async def get_replay_outputs(run_id: str):
    run = await asyncio.to_thread(_get_run_or_404, run_id)
    return await asyncio.to_thread(_load_outputs_or_409, run)


@router.post(
    "/replays/{run_id}/cancel",
    response_model=ReplayRunResponse,
    summary="Cancel Replay Run",
    responses={404: {"description": "Run not found"}, 409: {"description": "Run is not active"}},
)
async def cancel_replay(run_id: str):
    await asyncio.to_thread(_get_run_or_404, run_id)
    if not await get_replay_service().cancel(run_id):
        raise HTTPException(status_code=409, detail="Replay run is not active")
    return await asyncio.to_thread(_get_run_or_404, run_id)


@router.delete(
    "/replays/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Replay Run",
    responses={404: {"description": "Run not found"}, 409: {"description": "Run is still active"}},
)
async def delete_replay(run_id: str):
    run = await asyncio.to_thread(_get_run_or_404, run_id)
    if run["status"] in ("queued", "running"):
        raise HTTPException(status_code=409, detail="Cancel the run before deleting it")
    await asyncio.to_thread(get_replay_service().delete_run, run_id)
