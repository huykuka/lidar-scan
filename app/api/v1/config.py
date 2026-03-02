"""
Configuration import/export API endpoints.
Allows exporting the entire system configuration (lidars + fusions) to JSON
and importing it back.
"""
import json
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.repositories import NodeRepository, EdgeRepository

router = APIRouter()


class ConfigurationExport(BaseModel):
    """Configuration export model"""
    version: str = "2.0"
    nodes: list
    edges: list


class ConfigurationImport(BaseModel):
    """Configuration import model"""
    nodes: list = []
    edges: list = []
    merge: bool = False  # If False, replaces all configs. If True, merges with existing.


@router.get("/config/export")
def export_configuration():
    """
    Export all node and edge configurations as JSON.
    
    Returns:
        JSON object containing the node graph
    """
    node_repo = NodeRepository()
    edge_repo = EdgeRepository()
    
    nodes = node_repo.list()
    edges = edge_repo.list()
    
    config = ConfigurationExport(
        nodes=nodes,
        edges=edges
    )
    
    # Return as downloadable JSON file
    return Response(
        content=config.model_dump_json(indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=lidar-config.json"
        }
    )


@router.post("/config/import")
def import_configuration(config: ConfigurationImport):
    """
    Import node and edge configurations from JSON.
    """
    node_repo = NodeRepository()
    edge_repo = EdgeRepository()
    
    try:
        # If not merging, delete all existing configurations
        if not config.merge:
            existing_nodes = node_repo.list()
            for node in existing_nodes:
                node_repo.delete(node["id"])
            # Edge logic is handled by deleting nodes (cascade) or via save_all
        
        # Import nodes
        imported_nodes = []
        for node_config in config.nodes:
            node_id = node_repo.upsert(node_config)
            imported_nodes.append(node_id)
            
        # Recreate edges if we are replacing entirely
        if not config.merge:
             edge_repo.save_all(config.edges)
        
        return {
            "success": True,
            "mode": "merge" if config.merge else "replace",
            "imported": {
                "nodes": len(imported_nodes),
                "edges": len(config.edges) if not config.merge else 0
            },
            "node_ids": imported_nodes
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Import failed: {str(e)}"
        )


@router.post("/config/validate")
def validate_configuration(config: ConfigurationImport):
    """
    Validate a node configuration without importing it.
    """
    errors = []
    warnings = []
    
    seen_ids = set()
    
    for i, node in enumerate(config.nodes):
        if not node.get("name"):
            errors.append(f"Node #{i}: missing 'name'")
        if not node.get("type"):
            errors.append(f"Node #{i}: missing 'type'")
            
        if "id" in node:
            if node["id"] in seen_ids:
                errors.append(f"Node #{i}: duplicate ID '{node['id']}'")
            seen_ids.add(node["id"])
    
    is_valid = len(errors) == 0
    
    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "nodes": len(config.nodes),
            "edges": len(config.edges)
        }
    }
