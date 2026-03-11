"""Nodes endpoint handlers - Pure business logic without routing configuration."""

import time
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

from app.repositories import NodeRepository, EdgeRepository
from app.services.nodes.instance import node_manager
from app.services.nodes.schema import node_schema_registry


class NodeCreateUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "MultiScan Left",
                    "type": "sensor",
                    "category": "sensor",
                    "enabled": True,
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
    config: Dict[str, Any] = {}
    x: Optional[float] = None
    y: Optional[float] = None


class NodeStatusToggle(BaseModel):
    enabled: bool


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
    """Returns runtime status of all nodes based on their engine handlers"""
    # Build a unified status list from the running service
    nodes_status = []
    
    repo = NodeRepository()
    nodes = repo.list()
    
    for cnfg in nodes:
        node_id = cnfg["id"]
        node_instance = node_manager.nodes.get(node_id)
        
        if node_instance and hasattr(node_instance, "get_status"):
            status = node_instance.get_status(node_manager.node_runtime_status)
            # Re-add category from DB if not in runtime status
            status["category"] = cnfg["category"]
            status["enabled"] = cnfg["enabled"]
            
            # Auto-generate topic: {node_name}_{node_id[:8]}
            node_name = getattr(node_instance, "name", node_id)
            status["topic"] = f"{node_name}_{node_id[:8]}"
            
            # Add throttling stats from NodeManager
            throttle_stats = node_manager.get_throttle_stats(node_id)
            status.update(throttle_stats)
            
            nodes_status.append(status)
        else:
            nodes_status.append({
                "id": node_id,
                "name": cnfg["name"],
                "type": cnfg["type"],
                "category": cnfg["category"],
                "enabled": cnfg["enabled"],
                "running": False,
                "last_error": "Node instance not found"
            })
    
    return {"nodes": nodes_status}