"""
Calibration API endpoints.

Provides REST API for triggering calibrations, accepting/rejecting results,
viewing history, and rollback functionality.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.repositories import calibration_orm
from app.repositories.node_orm import NodeRepository
from app.services.nodes.instance import node_manager
from app.modules.calibration.calibration_node import CalibrationNode

router = APIRouter()


# --- Request/Response Models ---

class TriggerCalibrationRequest(BaseModel):
    """Request body for triggering calibration."""
    reference_sensor_id: Optional[str] = None
    source_sensor_ids: Optional[List[str]] = None
    sample_frames: int = 1


class AcceptCalibrationRequest(BaseModel):
    """Request body for accepting calibration."""
    sensor_ids: Optional[List[str]] = None  # None = all pending


class RollbackRequest(BaseModel):
    """Request body for rollback operation."""
    timestamp: str


# --- Endpoints ---

@router.post("/calibration/{node_id}/trigger")
async def trigger_calibration(
    node_id: str,
    request: TriggerCalibrationRequest
):
    """
    Trigger ICP calibration on buffered sensor data.
    
    Args:
        node_id: Calibration node ID
        request: Calibration parameters
        
    Returns:
        Calibration results with fitness, RMSE, and quality metrics
    """
    # Get calibration node from manager
    node = node_manager.nodes.get(node_id)
    
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    
    if not isinstance(node, CalibrationNode):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} is not a calibration node (type: {type(node).__name__})"
        )
    
    # Run calibration
    try:
        results = await node.trigger_calibration({
            "reference_sensor_id": request.reference_sensor_id,
            "source_sensor_ids": request.source_sensor_ids
        })
        
        return {
            "success": True,
            "results": results.get("results", {}),
            "pending_approval": not node.auto_save
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calibration failed: {str(e)}")


@router.post("/calibration/{node_id}/accept")
async def accept_calibration(
    node_id: str,
    request: AcceptCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    Accept pending calibration and apply to sensors.
    
    Args:
        node_id: Calibration node ID
        request: Acceptance parameters
        db: Database session
        
    Returns:
        List of accepted sensor IDs
    """
    # Get calibration node from manager
    node = node_manager.nodes.get(node_id)
    
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    
    if not isinstance(node, CalibrationNode):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} is not a calibration node"
        )
    
    # Accept calibration
    try:
        accepted = await node.accept_calibration(
            sensor_ids=request.sensor_ids,
            db=db
        )
        
        return {
            "success": True,
            "accepted": accepted
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept calibration: {str(e)}")


@router.post("/calibration/{node_id}/reject")
async def reject_calibration(node_id: str):
    """
    Reject pending calibration (discard results).
    
    Args:
        node_id: Calibration node ID
        
    Returns:
        Success status
    """
    # Get calibration node from manager
    node = node_manager.nodes.get(node_id)
    
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    
    if not isinstance(node, CalibrationNode):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} is not a calibration node"
        )
    
    # Reject calibration
    await node.reject_calibration()
    
    return {"success": True}


@router.get("/calibration/history/{sensor_id}")
async def get_calibration_history(
    sensor_id: str,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Retrieve calibration history for a sensor.
    
    Args:
        sensor_id: Sensor node ID
        limit: Maximum number of records to return
        db: Database session
        
    Returns:
        List of calibration records
    """
    try:
        records = calibration_orm.get_calibration_history(
            db=db,
            sensor_id=sensor_id,
            limit=limit
        )
        
        return {
            "sensor_id": sensor_id,
            "history": [r.to_dict() for r in records]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")


@router.post("/calibration/rollback/{sensor_id}")
async def rollback_calibration(
    sensor_id: str,
    request: RollbackRequest,
    db: Session = Depends(get_db)
):
    """
    Rollback sensor to a previous calibration state.
    
    Args:
        sensor_id: Sensor node ID
        request: Timestamp of calibration to restore
        db: Database session
        
    Returns:
        Rollback confirmation with restored timestamp
    """
    # Find the calibration record
    record = calibration_orm.get_calibration_by_timestamp(
        db=db,
        sensor_id=sensor_id,
        timestamp=request.timestamp
    )
    
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Calibration record not found for sensor {sensor_id} at {request.timestamp}"
        )
    
    if not record.accepted:
        raise HTTPException(
            status_code=400,
            detail="Cannot rollback to a calibration that was not accepted"
        )
    
    # Get the sensor node
    sensor_node = node_manager.nodes.get(sensor_id)
    
    if sensor_node is None:
        raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
    
    # Update sensor configuration with the rolled-back pose
    try:
        import json
        pose_after = json.loads(record.pose_after_json)
        
        # Update sensor config in database
        repo = NodeRepository()
        
        # Get existing config or empty dict
        existing_config = sensor_node.config if hasattr(sensor_node, 'config') else {}
        
        repo.update_node_config(
            sensor_id,
            {
                **existing_config,
                "x": pose_after["x"],
                "y": pose_after["y"],
                "z": pose_after["z"],
                "roll": pose_after["roll"],
                "pitch": pose_after["pitch"],
                "yaw": pose_after["yaw"]
            }
        )
        
        # Trigger DAG reload
        node_manager.reload_config()
        
        return {
            "success": True,
            "sensor_id": sensor_id,
            "restored_to": request.timestamp
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}")


@router.get("/calibration/statistics/{sensor_id}")
async def get_calibration_statistics(
    sensor_id: str,
    db: Session = Depends(get_db)
):
    """
    Get statistical summary of calibration attempts for a sensor.
    
    Args:
        sensor_id: Sensor node ID
        db: Database session
        
    Returns:
        Statistics including total attempts, accepted count, averages
    """
    try:
        stats = calibration_orm.get_calibration_statistics(db=db, sensor_id=sensor_id)
        
        return {
            "sensor_id": sensor_id,
            **stats
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch statistics: {str(e)}")
