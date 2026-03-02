from typing import Any, Dict, List, Optional
from fastapi import APIRouter
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
    """Creates a single edge."""
    import uuid
    repo = EdgeRepository()
    data = edge.model_dump()
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

@router.delete("/edges/{edge_id}")
async def delete_edge(edge_id: str):
    """Deletes a single edge by id."""
    repo = EdgeRepository()
    edges = [e for e in repo.list() if e.get("id") != edge_id]
    repo.save_all(edges)
    return {"status": "deleted", "id": edge_id}

@router.post("/edges/bulk")
async def save_edges_bulk(edges: List[EdgeCreateUpdate]):
    """Saves the entire graph of edges sent from the front-end canvas"""
    repo = EdgeRepository()
    repo.save_all([e.model_dump() for e in edges])
    return {"status": "success"}
