from fastapi import APIRouter
from app.core.config import settings
from app.services.nodes.instance import node_manager
import asyncio

router = APIRouter()

@router.get("/status")
async def get_status():
    """System status endpoint"""
    return {
        "is_running": node_manager.is_running,
        "active_sensors": [s.id for s in node_manager.nodes.values()],
        "version": settings.VERSION
    }

@router.post("/start")
async def start_system():
    if not node_manager.is_running:
        node_manager.load_config()
        node_manager.start(asyncio.get_running_loop())
    return {"status": "success", "is_running": node_manager.is_running}

@router.post("/stop")
async def stop_system():
    if node_manager.is_running:
        node_manager.stop()
    return {"status": "success", "is_running": node_manager.is_running}
