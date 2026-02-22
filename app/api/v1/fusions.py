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

@router.get("/fusions")
async def get_fusions():
    return {"fusions": fusion_repo.list()}

@router.post("/fusions")
async def save_fusion_route(fusion: FusionModel):
    saved_id = fusion_repo.upsert(fusion.dict())
    return {"status": "success", "id": saved_id}

@router.delete("/fusions/{fusion_id}")
async def delete_fusion_route(fusion_id: str):
    fusion_repo.delete(fusion_id)
    return {"status": "success"}
