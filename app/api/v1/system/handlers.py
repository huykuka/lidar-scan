"""System endpoint handlers - Pure business logic without routing configuration."""

from app.core.config import settings
from app.services.nodes.instance import node_manager
import asyncio


async def get_status():
    """Get system status and active sensors."""
    return {
        "is_running": node_manager.is_running,
        "active_sensors": [s.id for s in node_manager.nodes.values()],
        "version": settings.VERSION
    }


async def start_system():
    """Start the pipeline engine."""
    if not node_manager.is_running:
        node_manager.load_config()
        node_manager.start(asyncio.get_running_loop())
    return {"status": "success", "is_running": node_manager.is_running}


async def stop_system():
    """Stop the pipeline engine."""
    if node_manager.is_running:
        node_manager.stop()
    return {"status": "success", "is_running": node_manager.is_running}