"""
Configuration import/export API endpoints.
Allows exporting the entire system configuration (lidars + fusions) to JSON
and importing it back.
"""
import json
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.repositories import LidarRepository, FusionRepository


router = APIRouter()


class ConfigurationExport(BaseModel):
    """Configuration export model"""
    version: str = "1.0"
    lidars: list
    fusions: list


class ConfigurationImport(BaseModel):
    """Configuration import model"""
    lidars: list = []
    fusions: list = []
    merge: bool = False  # If False, replaces all configs. If True, merges with existing.


@router.get("/config/export")
def export_configuration():
    """
    Export all lidar and fusion configurations as JSON.
    
    Returns:
        JSON object containing all lidars and fusions
    """
    lidar_repo = LidarRepository()
    fusion_repo = FusionRepository()
    
    lidars = lidar_repo.list()
    fusions = fusion_repo.list()
    
    config = ConfigurationExport(
        lidars=lidars,
        fusions=fusions
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
    Import lidar and fusion configurations from JSON.
    
    Args:
        config: Configuration to import
    
    Returns:
        Summary of import operation
    
    The import can work in two modes:
    - merge=False (default): Deletes all existing configs and imports new ones
    - merge=True: Keeps existing configs and adds/updates from import
    """
    lidar_repo = LidarRepository()
    fusion_repo = FusionRepository()
    
    try:
        # If not merging, delete all existing configurations
        if not config.merge:
            existing_lidars = lidar_repo.list()
            for lidar in existing_lidars:
                lidar_repo.delete(lidar["id"])
            
            existing_fusions = fusion_repo.list()
            for fusion in existing_fusions:
                fusion_repo.delete(fusion["id"])
        
        # Import lidars
        imported_lidars = []
        for lidar_config in config.lidars:
            lidar_id = lidar_repo.upsert(lidar_config)
            imported_lidars.append(lidar_id)
        
        # Import fusions
        imported_fusions = []
        for fusion_config in config.fusions:
            fusion_id = fusion_repo.upsert(fusion_config)
            imported_fusions.append(fusion_id)
        
        return {
            "success": True,
            "mode": "merge" if config.merge else "replace",
            "imported": {
                "lidars": len(imported_lidars),
                "fusions": len(imported_fusions)
            },
            "lidar_ids": imported_lidars,
            "fusion_ids": imported_fusions
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Import failed: {str(e)}"
        )


@router.post("/config/validate")
def validate_configuration(config: ConfigurationImport):
    """
    Validate a configuration without importing it.
    
    Args:
        config: Configuration to validate
    
    Returns:
        Validation results with any errors or warnings
    """
    errors = []
    warnings = []
    
    # Validate lidars
    seen_ids = set()
    seen_topics = set()
    
    for i, lidar in enumerate(config.lidars):
        # Check required fields
        if not lidar.get("name"):
            errors.append(f"Lidar #{i}: missing 'name'")
        if not lidar.get("launch_args"):
            errors.append(f"Lidar #{i}: missing 'launch_args'")
        
        # Check for duplicate IDs
        if "id" in lidar:
            if lidar["id"] in seen_ids:
                errors.append(f"Lidar #{i}: duplicate ID '{lidar['id']}'")
            seen_ids.add(lidar["id"])
        
        # Check for duplicate topic_prefix
        if "topic_prefix" in lidar:
            if lidar["topic_prefix"] in seen_topics:
                warnings.append(f"Lidar #{i}: duplicate topic_prefix '{lidar['topic_prefix']}' (will be auto-resolved)")
            seen_topics.add(lidar["topic_prefix"])
    
    # Validate fusions
    seen_fusion_ids = set()
    
    for i, fusion in enumerate(config.fusions):
        # Check required fields
        if not fusion.get("name"):
            errors.append(f"Fusion #{i}: missing 'name'")
        if not fusion.get("topic"):
            errors.append(f"Fusion #{i}: missing 'topic'")
        if not fusion.get("sensor_ids"):
            warnings.append(f"Fusion #{i}: empty sensor_ids array")
        
        # Check for duplicate IDs
        if "id" in fusion:
            if fusion["id"] in seen_fusion_ids:
                errors.append(f"Fusion #{i}: duplicate ID '{fusion['id']}'")
            seen_fusion_ids.add(fusion["id"])
    
    is_valid = len(errors) == 0
    
    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "lidars": len(config.lidars),
            "fusions": len(config.fusions)
        }
    }
