"""Admin service — node type management.

Handles listing all scanned node definitions (with enabled/disabled state)
and toggling them on/off.  When a node type is disabled, all DAG node
instances of that type are also disabled.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import HTTPException
from pydantic import BaseModel

from app.core.logging import get_logger
from app.repositories import NodeRepository
from app.repositories.node_type_registry_orm import NodeTypeRegistryRepository
from app.services.nodes.schema import node_schema_registry

logger = get_logger(__name__)


class NodeTypeToggle(BaseModel):
    enabled: bool


class NodeTypeRecord(BaseModel):
    type: str
    display_name: str
    category: str
    description: str
    icon: str
    enabled: bool


async def list_node_types() -> List[NodeTypeRecord]:
    """Return every scanned node definition with its enabled state."""
    registry_repo = NodeTypeRegistryRepository()
    all_defs = node_schema_registry.get_all()

    # Build a lookup of enabled state from DB
    db_rows = registry_repo.list_all()
    enabled_map: Dict[str, bool] = {r["type"]: r["enabled"] for r in db_rows}

    result: List[NodeTypeRecord] = []
    for d in all_defs:
        result.append(
            NodeTypeRecord(
                type=d.type,
                display_name=d.display_name,
                category=d.category,
                description=d.description or "",
                icon=d.icon,
                enabled=enabled_map.get(d.type, True),
            )
        )
    return result


async def set_node_type_enabled(
        node_type: str, req: NodeTypeToggle
) -> Dict[str, Any]:
    """Enable or disable a node type.

    When disabling, all DAG node instances of that type are also disabled
    so the running system stops using them.
    """
    definition = node_schema_registry.get(node_type)
    if definition is None:
        raise HTTPException(status_code=404, detail=f"Node type '{node_type}' not found")

    registry_repo = NodeTypeRegistryRepository()
    registry_repo.set_enabled(node_type, req.enabled)

    disabled_instances: List[str] = []

    if not req.enabled:
        # Disable all DAG node instances of this type
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
