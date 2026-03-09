from fastapi import APIRouter
from app.core.config import settings
from app.services.nodes.instance import node_manager
from app.api.v1.schemas.system import SystemStatusResponse, SystemControlResponse
import asyncio

router = APIRouter(tags=["System"])

@router.get("/status", response_model=SystemStatusResponse)
async def get_status():
    """System status endpoint"""
    return {
        "is_running": node_manager.is_running,
        "active_sensors": [s.id for s in node_manager.nodes.values()],
        "version": settings.VERSION
    }

@router.post("/start", response_model=SystemControlResponse)
async def start_system():
    """Start the pipeline engine."""
    if not node_manager.is_running:
        node_manager.load_config()
        node_manager.start(asyncio.get_running_loop())
    return {"status": "success", "is_running": node_manager.is_running}

@router.post("/stop", response_model=SystemControlResponse)
async def stop_system():
    """Stop the pipeline engine."""
    if node_manager.is_running:
        node_manager.stop()
    return {"status": "success", "is_running": node_manager.is_running}
