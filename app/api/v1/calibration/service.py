"""Calibration endpoint handlers - Pure business logic without routing configuration."""

from typing import Any, Dict, List, Optional
import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories import calibration_orm
from app.repositories.node_orm import NodeRepository
from app.services.nodes.instance import node_manager
from app.modules.calibration.calibration_node import CalibrationNode
from .dto import TriggerCalibrationRequest, AcceptCalibrationRequest, RollbackRequest


async def trigger_calibration(node_id: str, request: TriggerCalibrationRequest):
    """
    Trigger ICP calibration on buffered sensor data.

    Args:
        node_id: Calibration node ID
        request: Calibration parameters

    Returns:
        Calibration results with fitness, RMSE, and quality metrics
    """
    node = node_manager.nodes.get(node_id)

    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    if not isinstance(node, CalibrationNode):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} is not a calibration node (type: {type(node).__name__})"
        )

    try:
        results = await node.trigger_calibration({
            "reference_sensor_id": request.reference_sensor_id,
            "source_sensor_ids": request.source_sensor_ids,
            "sample_frames": getattr(request, "sample_frames", 5)
        })

        return {
            "success": True,
            "results": results.get("results", {}),
            "pending_approval": not node.auto_save,
            "run_id": results.get("run_id")
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calibration failed: {str(e)}")


async def accept_calibration(node_id: str, request: AcceptCalibrationRequest, db: Session):
    """
    Accept pending calibration and apply to sensors.

    Args:
        node_id: Calibration node ID
        request: Acceptance parameters
        db: Database session

    Returns:
        List of accepted sensor IDs
    """
    node = node_manager.nodes.get(node_id)

    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    if not isinstance(node, CalibrationNode):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} is not a calibration node"
        )

    try:
        result = await node.accept_calibration(
            sensor_ids=request.sensor_ids,
            db=db
        )
        return {
            "success": result.get("success", True),
            "accepted": result.get("accepted", [])
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept calibration: {str(e)}")


async def reject_calibration(node_id: str):
    """
    Reject pending calibration (discard results).

    Args:
        node_id: Calibration node ID

    Returns:
        Dict with success bool and list of rejected sensor IDs
    """
    node = node_manager.nodes.get(node_id)

    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    if not isinstance(node, CalibrationNode):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} is not a calibration node"
        )

    # Capture rejected sensor IDs BEFORE clearing pending calibration
    rejected_ids = list((node._pending_calibration or {}).keys())

    await node.reject_calibration()

    return {"success": True, "rejected": rejected_ids}


async def get_calibration_status(node_id: str) -> Dict[str, Any]:
    """
    Get full calibration workflow state for a node.

    Args:
        node_id: Calibration node ID

    Returns:
        Full calibration status dict from CalibrationNode.get_calibration_status()
    """
    node = node_manager.nodes.get(node_id)

    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    if not isinstance(node, CalibrationNode):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} is not a calibration node"
        )

    return node.get_calibration_status()


async def get_calibration_history(
    sensor_id: str,
    limit: int,
    db: Session,
    source_sensor_id: Optional[str] = None,
    run_id: Optional[str] = None,
):
    """
    Retrieve calibration history for a sensor.

    Args:
        sensor_id: Sensor node ID (for backward compatibility)
        limit: Maximum number of records to return
        db: Database session
        source_sensor_id: Optional leaf sensor ID for provenance-based queries
        run_id: Optional run ID to filter records

    Returns:
        List of calibration records
    """
    try:
        if source_sensor_id:
            records = calibration_orm.get_calibration_history_by_source(
                db=db,
                source_sensor_id=source_sensor_id,
                limit=limit
            )
        else:
            records = calibration_orm.get_calibration_history(
                db=db,
                sensor_id=sensor_id,
                limit=limit,
                run_id=run_id,
            )

        return {
            "sensor_id": sensor_id,
            "history": [r.to_dict() for r in records]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")


async def rollback_calibration(sensor_id: str, request: RollbackRequest, db: Session):
    """
    Rollback sensor to a previous calibration state.

    Uses record_id (PK) for reliable lookup instead of timestamp.
    Creates a new 'rollback' history record referencing the original.

    Args:
        sensor_id: Sensor node ID
        request: RollbackRequest with record_id
        db: Database session

    Returns:
        Rollback confirmation with restored timestamp and new_record_id
    """
    from app.schemas.pose import Pose

    # Find the calibration record by PK
    record = calibration_orm.get_calibration_by_id(db=db, record_id=request.record_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Calibration record {request.record_id} not found"
        )

    if not record.accepted:
        raise HTTPException(
            status_code=400,
            detail="Cannot rollback to a calibration that was not accepted"
        )

    try:
        # Read current pose before rollback (for history record)
        repo = NodeRepository(session=db)
        existing_node = repo.get_by_id(sensor_id)
        if existing_node is None:
            raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")

        current_pose_dict = existing_node.get("pose") or {}
        pose_after = json.loads(record.pose_after_json)

        # Update sensor pose in database using nested entity (never flat keys)
        repo.update_node_pose(sensor_id, Pose(**pose_after))

        # Create a new 'rollback' history record
        rollback_record_id = uuid.uuid4().hex
        now_iso = datetime.now(timezone.utc).isoformat()
        calibration_orm.create_calibration_record(
            db=db,
            record_id=rollback_record_id,
            sensor_id=sensor_id,
            reference_sensor_id=record.reference_sensor_id or "",
            fitness=record.fitness,
            rmse=record.rmse,
            quality=record.quality,
            stages_used=json.loads(record.stages_used_json),
            pose_before=current_pose_dict,
            pose_after=pose_after,
            transformation_matrix=json.loads(record.transformation_matrix_json),
            accepted=True,
            accepted_at=now_iso,
            node_id=record.node_id,
            rollback_source_id=request.record_id,
            source_sensor_id=record.source_sensor_id,
            run_id=None,
        )

        # Trigger DAG reload
        await node_manager.reload_config()

        return {
            "success": True,
            "sensor_id": sensor_id,
            "restored_to": record.timestamp,
            "new_record_id": rollback_record_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}")


async def get_calibration_statistics(sensor_id: str, db: Session):
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
