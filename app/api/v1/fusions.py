from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from app.repositories import FusionRepository

router = APIRouter()
fusion_repo = FusionRepository()

class FusionModel(BaseModel):
    id: Optional[str] = None
    name: str
    topic: str
    sensor_ids: List[str]
    pipeline_name: Optional[str] = None
    enabled: Optional[bool] = None

@router.get("/fusions")
async def get_fusions():
    return {"fusions": fusion_repo.list()}

@router.post("/fusions")
async def save_fusion_route(fusion: FusionModel):
    saved_id = fusion_repo.upsert(fusion.dict())
    return {"status": "success", "id": saved_id}


@router.post("/fusions/{fusion_id}/enabled")
async def set_fusion_enabled(fusion_id: str, enabled: bool):
    """Enable/disable a fusion node, then reload config."""
    fusion_repo.set_enabled(fusion_id, enabled)
    from app.services.lidar.instance import lidar_service

    lidar_service.reload_config()
    return {"status": "success", "id": fusion_id, "enabled": enabled}

@router.delete("/fusions/{fusion_id}")
async def delete_fusion_route(fusion_id: str):
    fusion_repo.delete(fusion_id)
    return {"status": "success"}
