"""Service layer for DAG config GET and PUT operations.

Design contract:
- No user/session/version concurrency logic — last-write-wins.
- Simple optimistic lock via monotonic ``config_version`` integer.
- The _reload_lock check prevents two simultaneous PUTs or a PUT racing
  with an in-progress ``POST /nodes/reload``.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Dict, List, Tuple

from fastapi import HTTPException

from app.api.v1.schemas.dag import (
    DagConfigResponse,
    DagConfigSaveRequest,
    DagConfigSaveResponse,
)
from app.api.v1.schemas.edges import EdgeRecord
from app.api.v1.schemas.nodes import NodeRecord
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.repositories import EdgeRepository, NodeRepository
from app.repositories.dag_meta_orm import DagMetaRepository
from app.services.nodes.config_hasher import compute_node_config_hash, compute_node_config_hash_no_pose
from app.services.nodes.instance import node_manager

logger = get_logger(__name__)

# Prefix that identifies client-generated temporary node IDs.
_TEMP_ID_PREFIX = "__new__"


def _is_temp_id(node_id: str) -> bool:
    """Return True when the node ID is a client-side temporary placeholder."""
    return node_id.startswith(_TEMP_ID_PREFIX)


def _classify_dag_changes(
    new_nodes: List[NodeRecord],
    new_edges: List[Dict],
    existing_nodes: List[Dict],
    existing_edges: List[Dict],
) -> Tuple[str, List[str]]:
    """Classify the type of changes between the existing and incoming DAG snapshot.

    Returns a tuple of ``(change_type, changed_node_ids)`` where *change_type* is one of:

    - ``"topology"``     — node set or edge set changed (full reload required)
    - ``"param_change"`` — node config/enabled/visible changed (selective reload per node)
    - ``"pose_only"``    — only pose changed (hot-update without process restart)
    - ``"no_change"``    — only cosmetic fields changed (x, y, name); no reload needed

    Args:
        new_nodes: Incoming nodes from the PUT request.
        new_edges: Remapped edges after temp-ID resolution (dicts).
        existing_nodes: Current nodes from DB before the transaction.
        existing_edges: Current edges from DB before the transaction.

    Returns:
        Tuple of (change_type, changed_node_ids).
    """
    # ── Topology check: node set ───────────────────────────────────────
    existing_ids = {n["id"] for n in existing_nodes}
    # Exclude temp-ID nodes from the new set (they are always additions)
    new_ids = {n.id for n in new_nodes if not _is_temp_id(n.id)}

    if existing_ids != new_ids:
        return "topology", []

    # If any new node has a temp ID, that is also a topology change (addition)
    if any(_is_temp_id(n.id) for n in new_nodes):
        return "topology", []

    # ── Topology check: edge set ───────────────────────────────────────
    def _edge_key(e: Dict) -> str:
        return json.dumps(
            {
                "source_node": e.get("source_node"),
                "source_port": e.get("source_port"),
                "target_node": e.get("target_node"),
                "target_port": e.get("target_port"),
            },
            sort_keys=True,
        )

    existing_edge_keys = {_edge_key(e) for e in existing_edges}
    new_edge_keys = {_edge_key(e.model_dump() if hasattr(e, "model_dump") else e) for e in new_edges}

    if existing_edge_keys != new_edge_keys:
        return "topology", []

    # ── Param change check: compare config hashes ─────────────────────
    changed_ids: List[str] = []
    pose_only_ids: List[str] = []
    for node in new_nodes:
        stored_hash = node_manager._config_hash_store.get(node.id)
        if stored_hash is None:
            changed_ids.append(node.id)
            continue
        new_hash = compute_node_config_hash(node.model_dump())
        if new_hash != stored_hash:
            # Full hash differs — check if only pose changed
            new_hash_no_pose = compute_node_config_hash_no_pose(node.model_dump())
            stored_hash_no_pose = node_manager._config_hash_store.get(f"{node.id}:no_pose")
            if stored_hash_no_pose and new_hash_no_pose == stored_hash_no_pose:
                pose_only_ids.append(node.id)
            else:
                changed_ids.append(node.id)

    # If any node has a real config change, do selective reload for all changed
    if changed_ids:
        return "param_change", changed_ids + pose_only_ids

    # If only pose changed, hot-update without process restart
    if pose_only_ids:
        return "pose_only", pose_only_ids

    return "no_change", []


async def get_dag_config() -> DagConfigResponse:
    """Read all nodes, edges and the current config_version from the DB.

    Runs synchronous SQLite queries on a background thread to avoid blocking
    the async event loop when SQLite is write-locked by a concurrent save.

    Returns:
        ``DagConfigResponse`` with current snapshot.
    """
    def _read_from_db():
        node_repo = NodeRepository()
        edge_repo = EdgeRepository()
        meta_repo = DagMetaRepository()

        raw_nodes: List[dict] = node_repo.list()
        raw_edges: List[dict] = edge_repo.list()
        version: int = meta_repo.get_version()
        return raw_nodes, raw_edges, version

    raw_nodes, raw_edges, version = await asyncio.to_thread(_read_from_db)

    nodes = [NodeRecord(**n) for n in raw_nodes]
    edges = [EdgeRecord(**e) for e in raw_edges]

    return DagConfigResponse(config_version=version, nodes=nodes, edges=edges)


async def save_dag_config(req: DagConfigSaveRequest) -> DagConfigSaveResponse:
    """Atomically replace nodes + edges, increment version, then reload smartly.

    Steps:
    1. Reject immediately if ``_reload_lock`` is held (409).
    2. Read current version; reject if stale (409).
    3. Snapshot existing nodes + edges for diff (before transaction).
    4. Within a single DB session/transaction:
       a. Determine which node IDs are new (temp) vs existing.
       b. Delete nodes that are no longer in the request.
       c. Upsert all requested nodes, collecting temp→real ID remapping.
       d. Replace all edges (via ``EdgeRepository.save_all``), applying
          the ID remap to ``source_node`` / ``target_node`` references.
       e. Increment ``config_version`` by 1.
       f. Commit.
    5. Classify changes and trigger the appropriate reload:
       - topology     → full ``reload_config()``
       - param_change → ``selective_reload_node()`` per changed node
       - no_change    → skip reload
    6. Return ``DagConfigSaveResponse`` with reload_mode and reloaded_node_ids.

    On any exception inside the DB block the session is rolled back and a
    500 is raised.  The ``config_version`` is NOT incremented on failure.

    Args:
        req: Validated ``DagConfigSaveRequest`` from the PUT handler.

    Returns:
        ``DagConfigSaveResponse`` with new version and any ID mappings.

    Raises:
        HTTPException(409): Lock held or version conflict.
        HTTPException(500): DB or reload failure.
    """
    # ── Step 1: Lock check ──────────────────────────────────────────────────
    if node_manager._reload_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="A configuration reload is already in progress. Please wait and retry.",
        )

    # ── Step 2: Version check ───────────────────────────────────────────────
    meta_repo = DagMetaRepository()
    current_version = meta_repo.get_version()
    if current_version != req.base_version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Version conflict: base_version={req.base_version} but current "
                f"version is {current_version}. Another save has occurred. "
                "Please reload and reapply your changes."
            ),
        )

    # ── Step 3: Snapshot existing state for diff ────────────────────────────
    snapshot_node_repo = NodeRepository()
    snapshot_edge_repo = EdgeRepository()
    existing_nodes_snapshot = snapshot_node_repo.list()
    existing_edges_snapshot = snapshot_edge_repo.list()

    # ── Step 4: Atomic DB transaction ───────────────────────────────────────
    node_id_map: Dict[str, str] = {}
    new_version: int = current_version + 1

    session = SessionLocal()
    try:
        node_repo = NodeRepository(session=session)
        edge_repo = EdgeRepository(session=session)
        meta_repo_tx = DagMetaRepository(session=session)

        # Get existing node IDs from DB (to detect deletions)
        existing_nodes = node_repo.list()
        existing_ids = {n["id"] for n in existing_nodes}

        # Determine IDs that will be kept (non-temp) from the request
        requested_ids = set()
        for node in req.nodes:
            if not _is_temp_id(node.id):
                requested_ids.add(node.id)

        # Delete nodes that are in DB but NOT in the incoming request
        ids_to_delete = existing_ids - requested_ids
        for nid in ids_to_delete:
            node_repo.delete(nid)  # also cascades edges via NodeRepository.delete

        # Upsert all requested nodes
        for node in req.nodes:
            payload = node.model_dump()
            if _is_temp_id(node.id):
                # Assign a new server-generated UUID
                new_id = uuid.uuid4().hex
                payload["id"] = new_id
                node_id_map[node.id] = new_id
            node_repo.upsert(payload)

        # Build remapped edge list
        remapped_edges = []
        for edge in req.edges:
            e_dict = edge.model_dump()
            e_dict["source_node"] = node_id_map.get(e_dict["source_node"], e_dict["source_node"])
            e_dict["target_node"] = node_id_map.get(e_dict["target_node"], e_dict["target_node"])
            remapped_edges.append(e_dict)

        # Replace all edges
        edge_repo.save_all(remapped_edges)

        # Increment version within the same transaction
        new_version = meta_repo_tx.increment_version(session)

        session.commit()

    except HTTPException:
        session.rollback()
        session.close()
        raise
    except Exception as exc:
        session.rollback()
        session.close()
        logger.error(f"save_dag_config: DB transaction failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Save failed: {str(exc)}")
    finally:
        session.close()

    # ── Step 5: Classify changes and trigger the appropriate reload ──────────
    # Use the pre-transaction snapshot for diff — new_edges still use original IDs
    # but the remapped_edges reflect the actual persisted state. We pass req.edges
    # (with ID remap applied) to the classifier.
    change_type, changed_ids = _classify_dag_changes(
        new_nodes=req.nodes,
        new_edges=req.edges,  # type: ignore[arg-type]
        existing_nodes=existing_nodes_snapshot,
        existing_edges=existing_edges_snapshot,
    )

    reload_mode: str
    reloaded_ids: List[str]

    try:
        if change_type == "topology":
            await node_manager.reload_config()
            reload_mode = "full"
            reloaded_ids = []
        elif change_type == "param_change":
            for node_id in changed_ids:
                await node_manager.selective_reload_node(node_id)
            reload_mode = "selective"
            reloaded_ids = changed_ids
        elif change_type == "pose_only":
            for node_id in changed_ids:
                await node_manager.hot_update_node_pose(node_id)
            reload_mode = "selective"
            reloaded_ids = changed_ids
        else:  # no_change
            reload_mode = "none"
            reloaded_ids = []
    except Exception as exc:
        logger.error(f"save_dag_config: reload failed ({change_type}): {exc}")
        raise HTTPException(
            status_code=500, detail=f"Save succeeded but reload failed: {str(exc)}"
        )

    # ── Step 6: Return ───────────────────────────────────────────────────────
    return DagConfigSaveResponse(
        config_version=new_version,
        node_id_map=node_id_map,
        reload_mode=reload_mode,  # type: ignore[arg-type]
        reloaded_node_ids=reloaded_ids,
    )
