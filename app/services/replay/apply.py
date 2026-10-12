"""Promote a replay run's parameter overrides to the live pipeline.

Goes through ``save_dag_config`` (the same path as the Settings page) so version checks,
the reload lock and selective reload behave exactly like a normal save.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.repositories import NodeRepository
from app.repositories.replay_orm import ReplayRunRepository

from .runner import ReplayError
from .values import same_value, value_for_config

# Playback-source keys the replay pins itself; never a "pipeline changed" signal.
_PLAYBACK_PINNED = {"recording_id", "loopable", "throttle_ms"}


def _run_with_snapshot(run_id: str) -> Dict[str, Any]:
    run = ReplayRunRepository().get(run_id, include_snapshot=True)
    if run is None:
        raise ReplayError(f"Replay run {run_id} not found", 404)
    return run


def preview_apply(run_id: str) -> Dict[str, Any]:
    """What applying this run would change in the live pipeline (read-only)."""
    run = _run_with_snapshot(run_id)
    overrides: Dict[str, Dict[str, Any]] = run.get("overrides") or {}
    live = {n["id"]: n for n in NodeRepository().list()}

    changes: List[Dict[str, Any]] = []
    for node_id, params in overrides.items():
        node = live.get(node_id)
        for key, new in params.items():
            current = ((node or {}).get("config") or {}).get(key)
            changes.append({
                "node_id": node_id,
                "node_name": node["name"] if node else node_id[:8],
                "node_exists": node is not None,
                "key": key,
                "current": current,
                "new": new,
                "changed": node is not None and not same_value(current, new),
            })

    # Has the live pipeline moved on since the run? (other parameters differ from the snapshot)
    diverged: List[Dict[str, Any]] = []
    for snap in (run.get("config_snapshot") or {}).get("nodes", []):
        node = live.get(snap["id"])
        if node is None:
            diverged.append({"node_id": snap["id"], "node_name": snap.get("name", snap["id"][:8]),
                             "key": None, "run_value": None, "live_value": None})
            continue
        skip = set(overrides.get(snap["id"], {}))
        if snap.get("type") == "playback":
            skip |= _PLAYBACK_PINNED
        live_cfg, snap_cfg = node.get("config") or {}, snap.get("config") or {}
        for key in sorted((set(live_cfg) | set(snap_cfg)) - skip):
            if not same_value(live_cfg.get(key), snap_cfg.get(key)):
                diverged.append({
                    "node_id": snap["id"], "node_name": node["name"], "key": key,
                    "run_value": snap_cfg.get(key), "live_value": live_cfg.get(key),
                })

    return {
        "run_id": run_id,
        "label": run["label"],
        "changes": changes,
        "has_changes": any(c["changed"] for c in changes),
        "missing_nodes": [c["node_id"] for c in changes if not c["node_exists"]],
        "pipeline_changed_since_run": diverged,
    }


async def apply_to_pipeline(run_id: str) -> Dict[str, Any]:
    """Write the run's overrides into the saved DAG and reload the affected nodes."""
    # Imported here: the DAG service pulls in the whole node manager.
    from app.api.v1.dag.service import get_dag_config, save_dag_config
    from app.api.v1.schemas.dag import DagConfigSaveRequest

    run = _run_with_snapshot(run_id)
    overrides: Dict[str, Dict[str, Any]] = run.get("overrides") or {}
    if not overrides:
        raise ReplayError("This run has no parameter overrides to apply", 409)

    current = await get_dag_config()
    by_id = {n.id: n for n in current.nodes}
    missing = [nid for nid in overrides if nid not in by_id]
    if missing:
        raise ReplayError(f"Nodes no longer in the pipeline: {', '.join(m[:8] for m in missing)}", 409)

    nodes = []
    applied: List[Dict[str, Any]] = []
    for node in current.nodes:
        params = overrides.get(node.id)
        if params:
            config = dict(node.config)
            for key, new in params.items():
                if not same_value(config.get(key), new):
                    applied.append({"node_id": node.id, "node_name": node.name, "key": key,
                                    "old": config.get(key), "new": new})
                    config[key] = value_for_config(config.get(key), new)
            node = node.model_copy(update={"config": config})
        nodes.append(node)

    if not applied:
        raise ReplayError("The pipeline already has these values", 409)

    response = await save_dag_config(
        DagConfigSaveRequest(base_version=current.config_version, nodes=nodes, edges=current.edges)
    )
    return {
        "applied": applied,
        "config_version": response.config_version,
        "reload_mode": response.reload_mode,
        "reloaded_node_ids": response.reloaded_node_ids,
    }
