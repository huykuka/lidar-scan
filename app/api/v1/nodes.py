import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.repositories import NodeRepository, EdgeRepository
from app.services.nodes.instance import node_manager
from app.services.nodes.schema import node_schema_registry

router = APIRouter()

class NodeCreateUpdate(BaseModel):
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

@router.get("/nodes")
async def list_nodes():
    repo = NodeRepository()
    return repo.list()

@router.get("/nodes/definitions")
async def list_node_definitions():
    """Returns all available node types and their configuration schemas"""
    return node_schema_registry.get_all()



@router.get("/nodes/{node_id}")
async def get_node(node_id: str):
    repo = NodeRepository()
    node = repo.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node

@router.post("/nodes")
async def upsert_node(req: NodeCreateUpdate):
    """Create or update a node with proper error handling"""
    try:
        repo = NodeRepository()
        node_id = repo.upsert(req.model_dump())
        return {"status": "success", "id": node_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid node configuration: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create/update node: {str(e)}")

@router.put("/nodes/{node_id}/enabled")
async def set_node_enabled(node_id: str, req: NodeStatusToggle):
    """Enable/disable a node with error handling"""
    try:
        repo = NodeRepository()
        node = repo.get_by_id(node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        
        repo.set_enabled(node_id, req.enabled)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update node status: {str(e)}")

@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str):
    """Delete a node with proper error handling"""
    try:
        node_repo = NodeRepository()
        edge_repo = EdgeRepository()
        
        # Check if node exists
        node = node_repo.get_by_id(node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        
        # Delete the node dynamically from orchestrator
        node_manager.remove_node(node_id)
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete node: {str(e)}")

@router.post("/nodes/reload")
async def reload_all_config():
    """Reload all node configurations with error handling"""
    try:
        node_manager.reload_config()
        return {"status": "success", "message": "Configuration reloaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload configuration: {str(e)}")
    return {"status": "success"}

@router.get("/nodes/status/all")
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
