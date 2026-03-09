from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.repositories import EdgeRepository
from app.services.nodes.instance import node_manager

router = APIRouter()

class EdgeCreateUpdate(BaseModel):
    id: Optional[str] = None
    source_node: str
    source_port: str = "out"
    target_node: str
    target_port: str = "in"

@router.get("/edges")
async def list_edges():
    repo = EdgeRepository()
    return repo.list()

@router.post("/edges")
async def create_edge(edge: EdgeCreateUpdate):
    """Creates a single edge with proper error handling."""
    try:
        import uuid
        repo = EdgeRepository()
        data = edge.model_dump()
        
        # Validate that source and target nodes exist
        if data["source_node"] not in node_manager.nodes:
            raise HTTPException(status_code=400, detail=f"Source node '{data['source_node']}' not found")
        if data["target_node"] not in node_manager.nodes:
            raise HTTPException(status_code=400, detail=f"Target node '{data['target_node']}' not found")
        
        # Set defaults
        if not data.get("id"):
            data["id"] = str(uuid.uuid4())
        if not data.get("source_port"):
            data["source_port"] = "out"
        if not data.get("target_port"):
            data["target_port"] = "in"
            
        existing = repo.list()
        existing.append(data)
        repo.save_all(existing)
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create edge: {str(e)}")

@router.delete("/edges/{edge_id}")
async def delete_edge(edge_id: str):
    """Deletes a single edge by id with error handling."""
    try:
        repo = EdgeRepository()
        original_edges = repo.list()
        edges = [e for e in original_edges if e.get("id") != edge_id]
        
        if len(edges) == len(original_edges):
            raise HTTPException(status_code=404, detail="Edge not found")
            
        repo.save_all(edges)
        return {"status": "deleted", "id": edge_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete edge: {str(e)}")

@router.post("/edges/bulk")
async def save_edges_bulk(edges: List[EdgeCreateUpdate]):
    """Saves the entire graph of edges with validation and error handling"""
    try:
        repo = EdgeRepository()
        data = [e.model_dump() for e in edges]
        
        # Validate all edges before saving
        for edge in data:
            if edge["source_node"] not in node_manager.nodes:
                raise HTTPException(status_code=400, detail=f"Source node '{edge['source_node']}' not found")
            if edge["target_node"] not in node_manager.nodes:
                raise HTTPException(status_code=400, detail=f"Target node '{edge['target_node']}' not found")
        
        repo.save_all(data)
        return {"status": "success", "count": len(data)}
    except HTTPException:
        raise  
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save edges: {str(e)}")
