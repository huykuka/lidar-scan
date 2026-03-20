"""Nodes endpoint handlers - Pure business logic without routing configuration."""

import time
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

from app.core.logging import get_logger
from app.repositories import NodeRepository, EdgeRepository
from app.services.nodes.instance import node_manager
from app.services.nodes.schema import node_schema_registry

logger = get_logger(__name__)


class NodeCreateUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "MultiScan Left",
                    "type": "sensor",
                     "category": "sensor",
                     "enabled": True,
                     "visible": True,
                     "config": {
                        "lidar_type": "multiscan",
                        "hostname": "192.168.1.10",
                        "udp_receiver_ip": "192.168.1.100",
                        "port": 2115
                    },
                    "x": 120.0,
                    "y": 200.0
                },
                {
                    "name": "Point Cloud Fusion",
                    "type": "fusion",
                     "category": "fusion",
                     "enabled": True,
                     "visible": True,
                     "config": {
                        "fusion_method": "icp_registration", 
                        "distance_threshold": 0.05,
                        "max_iterations": 100
                    },
                    "x": 300.0,
                    "y": 200.0
                }
            ]
        }
    )
    
    id: Optional[str] = None
    name: str
    type: str
    category: str
    enabled: bool = True
    visible: bool = True
    config: Dict[str, Any] = {}
    x: Optional[float] = None
    y: Optional[float] = None


class NodeStatusToggle(BaseModel):
    enabled: bool


class NodeVisibilityToggle(BaseModel):
    visible: bool


async def list_nodes():
    """List all configured nodes."""
    repo = NodeRepository()
    return repo.list()


async def list_node_definitions():
    """Returns all available node types and their configuration schemas"""
    return node_schema_registry.get_all()


async def get_node(node_id: str):
    """Get a single node configuration by ID."""
    repo = NodeRepository()
    node = repo.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


async def upsert_node(req: NodeCreateUpdate):
    """Create or update a node."""
    repo = NodeRepository()
    node_id = repo.upsert(req.model_dump(exclude_none=True))
    return {"status": "success", "id": node_id}


async def set_node_enabled(node_id: str, req: NodeStatusToggle):
    """Toggle node enabled state."""
    repo = NodeRepository()
    repo.set_enabled(node_id, req.enabled)
    return {"status": "success"}


async def set_node_visible(node_id: str, req: NodeVisibilityToggle):
    """Toggle node visibility state."""
    from app.services.websocket.manager import SYSTEM_TOPICS
    from app.services.shared.topics import slugify_topic_prefix
    
    repo = NodeRepository()
    
    # Fetch node by ID; raise 404 if not found
    node = repo.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # Derive topic name and check against SYSTEM_TOPICS
    node_name = node.get("name", node_id)
    topic = f"{slugify_topic_prefix(node_name)}_{node_id[:8]}"
    
    if topic in SYSTEM_TOPICS:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot change visibility of system topic '{topic}'"
        )
    
    # Update visibility in database
    repo.set_visible(node_id, req.visible)
    
    # Update orchestrator state
    await node_manager.set_node_visible(node_id, req.visible)
    
    return {"status": "success"}


async def delete_node(node_id: str):
    """Delete a node and associated edges."""
    node_repo = NodeRepository()
    edge_repo = EdgeRepository()
    
    # Delete the node dynamically from orchestrator
    await node_manager.remove_node_async(node_id)
    node_repo.delete(node_id)
    
    # Delete any edges connected to this node
    all_edges = edge_repo.list()
    filtered_edges = [
        e for e in all_edges 
        if e.get("source_node") != node_id and e.get("target_node") != node_id
    ]
    if len(filtered_edges) < len(all_edges):
        edge_repo.save_all(filtered_edges)
        
    return {"status": "success"}


async def reload_all_config():
    """Reload all node configurations."""
    if node_manager._reload_lock.locked():
        raise HTTPException(status_code=409, detail="A configuration reload is already in progress. Please wait and retry.")
    
    await node_manager.reload_config()
    return {"status": "success"}


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
        elif node_instance and hasattr(node_instance, "get_status"):
            # Fallback for nodes not yet migrated (should not happen after B4-B8)
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                raw = node_instance.get_status(node_manager.node_runtime_status)
            entry = {
                "node_id": node_id,
                "operational_state": "RUNNING" if raw.get("running") else "STOPPED",
                "application_state": raw.get("application_state"),
                "error_message": raw.get("last_error"),
                "timestamp": time.time(),
            }
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