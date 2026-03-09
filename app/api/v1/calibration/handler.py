"""Calibration router configuration and endpoint metadata."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.models import get_db
from app.api.v1.schemas.calibration import (
    CalibrationTriggerResponse, 
    AcceptResponse, 
    RollbackResponse, 
    CalibrationHistoryResponse, 
    CalibrationStatsResponse
)
from app.api.v1.schemas.common import StatusResponse
from .service import (
    trigger_calibration, accept_calibration, reject_calibration,
    get_calibration_history, rollback_calibration, get_calibration_statistics,
    TriggerCalibrationRequest, AcceptCalibrationRequest, RollbackRequest
)


# Router configuration
router = APIRouter(tags=["Calibration"])

# Endpoint configurations
@router.post(
    "/calibration/{node_id}/trigger",
    response_model=CalibrationTriggerResponse,
    responses={
        400: {"description": "Invalid parameters or insufficient data"}, 
        404: {"description": "Node not found"}, 
        500: {"description": "Calibration algorithm error"}
    },
    summary="Trigger Calibration",
    description="Trigger ICP calibration on buffered sensor data.",
)
async def calibration_trigger_endpoint(node_id: str, request: TriggerCalibrationRequest):
    return await trigger_calibration(node_id, request)


@router.post(
    "/calibration/{node_id}/accept",
    response_model=AcceptResponse,
    responses={
        400: {"description": "Invalid request or no pending calibration"}, 
        404: {"description": "Node not found"}
    },
    summary="Accept Calibration",
    description="Accept pending calibration and apply to sensors.",
)
async def calibration_accept_endpoint(
    node_id: str, 
    request: AcceptCalibrationRequest,
    db: Session = Depends(get_db)
):
    return await accept_calibration(node_id, request, db)


@router.post(
    "/calibration/{node_id}/reject",
    response_model=StatusResponse,
    responses={404: {"description": "Node not found"}},
    summary="Reject Calibration",
    description="Reject pending calibration (discard results).",
)
async def calibration_reject_endpoint(node_id: str):
    return await reject_calibration(node_id)


@router.get(
    "/calibration/history/{sensor_id}",
    response_model=CalibrationHistoryResponse,
    responses={500: {"description": "Database error"}},
    summary="Get Calibration History",
    description="Retrieve calibration history for a sensor.",
)
async def calibration_history_endpoint(
    sensor_id: str,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    return await get_calibration_history(sensor_id, limit, db)


@router.post(
    "/calibration/rollback/{sensor_id}",
    response_model=RollbackResponse,
    responses={
        400: {"description": "Invalid rollback request or non-accepted calibration"}, 
        404: {"description": "Sensor or calibration record not found"}, 
        500: {"description": "Rollback operation failed"}
    },
    summary="Rollback Calibration",
    description="Rollback sensor to a previous calibration state.",
)
async def calibration_rollback_endpoint(
    sensor_id: str,
    request: RollbackRequest,
    db: Session = Depends(get_db)
):
    return await rollback_calibration(sensor_id, request, db)


@router.get(
    "/calibration/statistics/{sensor_id}",
    response_model=CalibrationStatsResponse,
    responses={500: {"description": "Database error"}},
    summary="Get Calibration Statistics",
    description="Get statistical summary of calibration attempts for a sensor.",
)
async def calibration_statistics_endpoint(
    sensor_id: str,
    db: Session = Depends(get_db)
):
    return await get_calibration_statistics(sensor_id, db)