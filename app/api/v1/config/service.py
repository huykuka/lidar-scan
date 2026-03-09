"""Configuration endpoint handlers - Pure business logic without routing configuration."""

import json
from typing import Dict, Any, List
from fastapi import HTTPException, Response
from pydantic import BaseModel, ConfigDict

from app.repositories import NodeRepository, EdgeRepository
from app.services.nodes.instance import node_manager


class ConfigurationExport(BaseModel):
    """Configuration export model"""
    version: str = "2.0"
    nodes: list
    edges: list


class ConfigurationImport(BaseModel):
    """Configuration import model"""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "nodes": [
                        {
                            "name": "Sensor A",
                            "type": "sensor",
                            "category": "sensor",
                            "enabled": True,
                            "config": {
                                "lidar_type": "multiscan",
                                "hostname": "192.168.1.10"
                            }
                        },
                        {
                            "name": "Fusion Node",
                            "type": "fusion",
                            "category": "fusion",
                            "enabled": True,
                            "config": {}
                        }
                    ],
                    "edges": [
                        {
                            "source_node": "sensor-id-1",
                            "source_port": "out",
                            "target_node": "fusion-id-1", 
                            "target_port": "in"
                        }
                    ],
                    "merge": False
                }
            ]
        }
    )
    
    nodes: list = []
    edges: list = []
    merge: bool = False  # If False, replaces all configs. If True, merges with existing.


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


async def import_configuration(config: ConfigurationImport):
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
        
        # Auto-trigger reload for replace mode to sync in-memory DAG
        reloaded = False
        if not config.merge:
            await node_manager.reload_config()
            reloaded = True
        
        return {
            "success": True,
            "mode": "merge" if config.merge else "replace",
            "imported": {
                "nodes": len(imported_nodes),
                "edges": len(config.edges) if not config.merge else 0
            },
            "node_ids": imported_nodes,
            "reloaded": reloaded
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Import failed: {str(e)}"
        )


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
    
    # Sensor-specific validation
    from app.modules.lidar.profiles import get_profile  # import inside function to avoid circular
    for i, node in enumerate(config.nodes):
        if node.get("type") == "sensor":
            node_name = node.get("name", f"#{i}")
            lidar_type = node.get("config", {}).get("lidar_type")
            if lidar_type is None:
                warnings.append(
                    f"Node '{node_name}': no lidar_type specified; defaulting to 'multiscan' (backward compat)."
                )
            else:
                try:
                    get_profile(lidar_type)
                except KeyError:
                    errors.append(
                        f"Node '{node_name}': lidar_type '{lidar_type}' is not a recognized SICK model."
                    )
    
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