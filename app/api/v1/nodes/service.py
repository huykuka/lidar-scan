"""Nodes endpoint handlers - Pure business logic without routing configuration.

Note: NodeCreateUpdate, upsert_node, and delete_node have been removed.
All node creation, update, and deletion is now performed atomically via
PUT /api/v1/dag/config. This module retains read operations (list, get, status)
and live-action toggles (enabled, visible, reload) which remain as direct
per-node calls.
"""

import time
from typing import Any, Dict, Optional, Set

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.repositories import NodeRepository
from app.services.nodes.instance import node_manager
from app.services.nodes.schema import node_schema_registry

logger = get_logger(__name__)


async def list_nodes():
    """List all configured nodes."""
    repo = NodeRepository()
    return repo.list()


async def list_node_definitions():
    """Returns only enabled node types and their configuration schemas."""
    from app.repositories.node_type_registry_orm import NodeTypeRegistryRepository

    registry_repo = NodeTypeRegistryRepository()
    db_rows = registry_repo.list_all()
    disabled_types = {r["type"] for r in db_rows if not r["enabled"]}
    return [d for d in node_schema_registry.get_all() if d.type not in disabled_types]


# ── Floor calibration (node-generic pose auto-level) ──────────────────────


def _get_calibratable_node(node_id: str):
    """Resolve any floor-calibratable source node (lidar, playback, visionary, pcd)."""
    from app.services.nodes.floor_calibration import FloorCalibrationMixin

    node = node_manager.nodes.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    if not isinstance(node, FloorCalibrationMixin):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} does not support floor calibration (type: {type(node).__name__})",
        )
    return node


class FloorCalibrationRequest(BaseModel):
    """Tunable parameters for floor-plane auto-level."""
    distance_threshold: float = Field(default=0.05, gt=0.0, description="RANSAC inlier distance (meters)")
    max_planes: int = Field(default=3, ge=1, le=10, description="Max planes to segment while searching for the floor")
    min_inliers: int = Field(default=50, ge=3, description="Minimum inliers for a plane to be considered")
    verticality_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Min |normal·up| to accept a plane as near-horizontal"
    )


async def calibrate_from_floor(node_id: str, request: FloorCalibrationRequest) -> Dict[str, Any]:
    """Level a source node's pose against the segmented floor plane and persist.

    One-shot calibration: segments the ground plane from the latest frame,
    derives the tilt correction, writes the updated pose to the database, and
    hot-updates the in-memory transformation. Mutually exclusive with IMU
    auto-level. Works for any pose-bearing source node (lidar, playback,
    visionary, pcd injection).

    Returns:
        Dict with the new pose values.
    """
    node = _get_calibratable_node(node_id)

    try:
        new_pose = node.calibrate_from_floor(
            distance_threshold=request.distance_threshold,
            max_planes=request.max_planes,
            min_inliers=request.min_inliers,
            verticality_threshold=request.verticality_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Hot-update the in-memory transformation so subsequent frames use the new pose
    await node_manager.hot_update_node_pose(node_id)

    return {
        "success": True,
        "node_id": node_id,
        "pose": new_pose.to_flat_dict(),
    }


# ── Node type registry (enable / disable) ─────────────────────────────────


class NodeTypeToggle(BaseModel):
    enabled: bool


class NodeTypeRecord(BaseModel):
    type: str
    display_name: str
    category: str
    description: str
    use_case: str | None
    version: str | None
    source: str  # "builtin" | "plugin"
    icon: str
    enabled: bool


async def list_node_type_registry() -> list[NodeTypeRecord]:
    """Return every scanned node definition with its enabled state."""
    from app.repositories.node_type_registry_orm import NodeTypeRegistryRepository
    from app.plugins import _loaded_plugins

    registry_repo = NodeTypeRegistryRepository()
    all_defs = node_schema_registry.get_all()

    db_rows = registry_repo.list_all()
    enabled_map: dict[str, bool] = {r["type"]: r["enabled"] for r in db_rows}

    plugin_types: set[str] = set()
    for types in _loaded_plugins.values():
        plugin_types |= types

    result: list[NodeTypeRecord] = []
    for d in all_defs:
        result.append(
            NodeTypeRecord(
                type=d.type,
                display_name=d.display_name,
                category=d.category,
                description=d.description or "",
                use_case=d.use_case,
                version=d.version,
                source="plugin" if d.type in plugin_types else "builtin",
                icon=d.icon,
                enabled=enabled_map.get(d.type, True),
            )
        )
    return result


async def set_node_type_enabled(node_type: str, req: NodeTypeToggle) -> dict:
    """Enable or disable a node type.

    When disabling, all DAG node instances of that type are also disabled.
    """
    from app.repositories.node_type_registry_orm import NodeTypeRegistryRepository

    definition = node_schema_registry.get(node_type)
    if definition is None:
        raise HTTPException(status_code=404, detail=f"Node type '{node_type}' not found")

    registry_repo = NodeTypeRegistryRepository()
    registry_repo.set_enabled(node_type, req.enabled)

    disabled_instances: list[str] = []

    if not req.enabled:
        node_repo = NodeRepository()
        all_nodes = node_repo.list()
        for node in all_nodes:
            if node["type"] == node_type and node.get("enabled", True):
                node_repo.set_enabled(node["id"], False)
                disabled_instances.append(node["id"])

        if disabled_instances:
            logger.info(
                "Disabled %d DAG instance(s) of type '%s': %s",
                len(disabled_instances),
                node_type,
                disabled_instances,
            )

    return {
        "status": "success",
        "type": node_type,
        "enabled": req.enabled,
        "disabled_instances": disabled_instances,
    }


async def get_node(node_id: str):
    """Get a single node configuration by ID."""
    repo = NodeRepository()
    node = repo.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


async def reload_all_config():
    """Reload all node configurations."""
    if node_manager._reload_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="A configuration reload is already in progress. Please wait and retry.",
        )

    try:
        await node_manager.reload_config()
    except RuntimeError as exc:
        # Raised when the reload watchdog aborts a hung reload. The lock has
        # already been released, so the client can safely retry.
        raise HTTPException(status_code=504, detail=str(exc))
    return {"status": "success"}


async def reload_single_node(node_id: str):
    """Selectively reload a single node in-place.

    Returns ``NodeReloadResponse`` on success.
    Raises:
        HTTPException(404): Node not in the running DAG.
        HTTPException(409): Reload lock is held.
        HTTPException(500): Reload failed (with rollback info in detail).
    """
    from app.api.v1.schemas.nodes import NodeReloadResponse

    # ── 409: Lock check ────────────────────────────────────────────────────
    if node_manager._reload_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="A configuration reload is already in progress. Please wait and retry.",
        )

    # ── 404 / disabled-node short-circuit ─────────────────────────────────
    # Disabled nodes are never added to node_manager.nodes, so attempting a
    # selective reload on them would always raise 404.  The DB was already
    # updated by the save step, so there is nothing more to do at runtime —
    # the new config will be picked up the next time the node is enabled.
    if node_id not in node_manager.nodes:
        node_record = NodeRepository().get_by_id(node_id)
        if node_record is not None and not node_record.get("enabled", True):
            # Node exists but is disabled — DB already saved, reload is a no-op.
            return {"status": "success", "note": "Node is disabled; config saved, no runtime reload needed."}
        raise HTTPException(
            status_code=404,
            detail=f"Node '{node_id}' not found in running DAG. Ensure the node is enabled.",
        )

    # ── Perform selective reload ───────────────────────────────────────────
    try:
        result = await node_manager.selective_reload_node(node_id)
    except RuntimeError as exc:
        # Raised when the reload watchdog aborts a hung selective reload. The
        # lock has already been released, so the client can safely retry.
        raise HTTPException(status_code=504, detail=str(exc))

    if result is not None and result.status == "error":
        if result.rolled_back:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Reload failed for node '{node_id}': {result.error_message}. "
                    "Node has been restored to previous configuration."
                ),
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Reload failed for node '{node_id}' and rollback also failed. "
                    "Node is offline. Manual intervention required."
                ),
            )

    ws_topic = getattr(result, "ws_topic", None) if result else None
    duration_ms = getattr(result, "duration_ms", 0.0) if result else 0.0

    return NodeReloadResponse(
        node_id=node_id,
        status="reloaded",
        duration_ms=duration_ms,
        ws_topic=ws_topic,
    )


async def get_reload_status():
    """Return the current state of the reload lock.

    Returns ``ReloadStatusResponse``.
    Spec: .opencode/plans/node-reload-improvement/api-spec.md § 3
    """
    from app.api.v1.schemas.nodes import ReloadStatusResponse

    locked = node_manager._reload_lock.locked()
    active_id: Optional[str] = node_manager._active_reload_node_id

    if not locked:
        estimated_completion_ms = None
    elif active_id is not None:
        estimated_completion_ms = 150  # selective reload estimate
    else:
        estimated_completion_ms = 3000  # full reload estimate

    return ReloadStatusResponse(
        locked=locked,
        reload_in_progress=locked,
        active_reload_node_id=active_id,
        estimated_completion_ms=estimated_completion_ms,
    )


async def get_nodes_status():
    """Returns runtime status of all nodes using the standardised emit_status() interface."""
    status_updates = []

    repo = NodeRepository()
    nodes = repo.list()

    for cnfg in nodes:
        node_id = cnfg["id"]
        node_instance = node_manager.nodes.get(node_id)

        if node_instance and hasattr(node_instance, "emit_status"):
            try:
                status = node_instance.emit_status()
                entry = status.model_dump()
            except Exception as e:
                logger.warning(f"[get_nodes_status] emit_status() failed for {node_id}: {e}")
                continue
        else:
            entry = {
                "node_id": node_id,
                "operational_state": "STOPPED",
                "application_state": None,
                "error_message": "Node instance not found",
                "timestamp": time.time(),
            }

        # Augment with DB metadata that the frontend needs
        entry["category"] = cnfg["category"]
        entry["enabled"] = cnfg["enabled"]
        entry["visible"] = cnfg.get("visible", True)
        entry["name"] = cnfg["name"]
        entry["type"] = cnfg["type"]

        # Derive WebSocket topic (None for invisible nodes)
        if node_instance and hasattr(node_instance, "_ws_topic"):
            entry["topic"] = node_instance._ws_topic
        else:
            entry["topic"] = None

        # Add throttling stats
        throttle_stats = node_manager.get_throttle_stats(node_id)
        entry.update(throttle_stats)

        status_updates.append(entry)

    return {"nodes": status_updates}


# ── Plugins ───────────────────────────────────────────────────────────────


class PluginRecord(BaseModel):
    name: str
    loaded: bool
    types: list[str]
    version: str | None = None
    description: str | None = None


async def list_plugins() -> list[PluginRecord]:
    """List all plugin directories with their load state, enriched with metadata."""
    from app.plugins import list_plugins as _list

    raw = _list()
    result: list[PluginRecord] = []
    for p in raw:
        version: str | None = None
        description: str | None = None
        for type_name in p["types"]:
            defn = node_schema_registry.get(type_name)
            if defn:
                version = defn.version
                description = defn.description
                break
        result.append(
            PluginRecord(
                name=p["name"],
                loaded=p["loaded"],
                types=p["types"],
                version=version,
                description=description,
            )
        )
    return result


async def remove_plugin(plugin_name: str) -> dict:
    """Unload and permanently delete a plugin from disk.

    Stops all running DAG instances of the plugin's node types before removal.
    """
    from app.repositories.edge_orm import EdgeRepository
    from app.plugins import remove_plugin as _remove

    try:
        removed_types = _remove(plugin_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to remove plugin '{plugin_name}': {exc}")

    if not removed_types:
        return {"status": "removed", "plugin": plugin_name, "types": [], "evicted_nodes": []}

    repo = NodeRepository()
    affected = [n for n in repo.list() if n.get("type") in removed_types]
    evicted: list[str] = []

    for node_data in affected:
        node_id = node_data["id"]
        try:
            repo.set_enabled(node_id, False)
        except Exception as exc:
            logger.warning("[remove_plugin] Could not disable node %r in DB: %s", node_id, exc)

        instance = node_manager.nodes.pop(node_id, None)
        if instance is not None:
            try:
                await node_manager._lifecycle_manager._stop_node_async(instance)
            except Exception as exc:
                logger.warning("[remove_plugin] Failed to stop node %r: %s", node_id, exc)
            evicted.append(node_id)

    if evicted:
        evicted_set = set(evicted)
        edge_repo = EdgeRepository()
        all_edges = edge_repo.list()
        surviving = [e for e in all_edges if e.get("source_node") not in evicted_set and e.get("target_node") not in evicted_set]
        if len(surviving) < len(all_edges):
            edge_repo.save_all(surviving)
        node_manager.edges_data = surviving
        node_manager.downstream_map = node_manager._config_loader.build_downstream_map(surviving)

    return {"status": "removed", "plugin": plugin_name, "types": sorted(removed_types), "evicted_nodes": evicted}


async def upload_plugin(zip_bytes: bytes) -> dict:
    """Validate zip structure (in-memory), install, then auto-load."""
    from app.plugins import validate_plugin_zip, install_plugin_zip
    import zipfile

    try:
        validate_plugin_zip(zip_bytes)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=422, detail="Uploaded file is not a valid zip archive.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        plugin_name, registered_types = install_plugin_zip(zip_bytes, auto_load=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Plugin install failed: {exc}")

    return {"status": "installed_and_loaded", "plugin": plugin_name, "types": sorted(registered_types)}
