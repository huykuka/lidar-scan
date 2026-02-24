from fastapi import APIRouter
from app.core.config import settings
from app.services.lidar.instance import lidar_service

router = APIRouter()

@router.get("/status")
async def get_status():
    """System status endpoint"""
    return {
        "is_running": lidar_service.is_running,
        "active_sensors": [s.id for s in lidar_service.sensors],
        "version": settings.VERSION
    }
