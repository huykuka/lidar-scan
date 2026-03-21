"""Service layer for DAG config GET and PUT operations.

Design contract:
- No user/session/version concurrency logic — last-write-wins.
- Simple optimistic lock via monotonic ``config_version`` integer.
- The _reload_lock check prevents two simultaneous PUTs or a PUT racing
  with an in-progress ``POST /nodes/reload``.
"""

from __future__ import annotations

import uuid
from typing import Dict, List

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
from app.services.nodes.instance import node_manager

logger = get_logger(__name__)

# Prefix that identifies client-generated temporary node IDs.
_TEMP_ID_PREFIX = "__new__"


def _is_temp_id(node_id: str) -> bool:
    """Return True when the node ID is a client-side temporary placeholder."""
    return node_id.startswith(_TEMP_ID_PREFIX)


async def get_dag_config() -> DagConfigResponse:
    """Read all nodes, edges and the current config_version from the DB.

    Returns:
        ``DagConfigResponse`` with current snapshot.
    """
    node_repo = NodeRepository()
    edge_repo = EdgeRepository()
    meta_repo = DagMetaRepository()

    raw_nodes: List[dict] = node_repo.list()
    raw_edges: List[dict] = edge_repo.list()
    version: int = meta_repo.get_version()

    nodes = [NodeRecord(**n) for n in raw_nodes]
    edges = [EdgeRecord(**e) for e in raw_edges]

    return DagConfigResponse(config_version=version, nodes=nodes, edges=edges)


async def save_dag_config(req: DagConfigSaveRequest) -> DagConfigSaveResponse:
    """Atomically replace nodes + edges, increment version, then reload.

    Steps:
    1. Reject immediately if ``_reload_lock`` is held (409).
    2. Read current version; reject if stale (409).
    3. Within a single DB session/transaction:
       a. Determine which node IDs are new (temp) vs existing.
       b. Delete nodes that are no longer in the request.
       c. Upsert all requested nodes, collecting temp→real ID remapping.
       d. Replace all edges (via ``EdgeRepository.save_all``), applying
          the ID remap to ``source_node`` / ``target_node`` references.
       e. Increment ``config_version`` by 1.
       f. Commit.
    4. Trigger ``node_manager.reload_config()`` outside the DB transaction.
    5. Return ``DagConfigSaveResponse``.

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

    # ── Step 3: Atomic DB transaction ───────────────────────────────────────
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

    # ── Step 4: Trigger runtime reload (outside DB transaction) ─────────────
    try:
        await node_manager.reload_config()
    except Exception as exc:
        logger.error(f"save_dag_config: reload_config() failed: {exc}")
        # Version was already committed; report error but don't rollback version.
        raise HTTPException(status_code=500, detail=f"Save succeeded but reload failed: {str(exc)}")

    # ── Step 5: Return ───────────────────────────────────────────────────────
    return DagConfigSaveResponse(config_version=new_version, node_id_map=node_id_map)
