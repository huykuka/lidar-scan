"""System router configuration and endpoint metadata."""

from fastapi import APIRouter
from app.api.v1.schemas.system import SystemStatusResponse, SystemControlResponse
from .handlers import get_status, start_system, stop_system


# Router configuration
router = APIRouter(tags=["System"])

# Endpoint configurations
@router.get(
    "/status",
    response_model=SystemStatusResponse,
    summary="Get System Status",
    description="Get current system status including running state, active sensors, and version.",
)
async def status_endpoint():
    return await get_status()


@router.post(
    "/start",
    response_model=SystemControlResponse,
    summary="Start System",
    description="Start the pipeline engine and begin processing.",
)
async def start_endpoint():
    return await start_system()


@router.post(
    "/stop",
    response_model=SystemControlResponse,
    summary="Stop System", 
    description="Stop the pipeline engine and halt processing.",
)
async def stop_endpoint():
    return await stop_system()