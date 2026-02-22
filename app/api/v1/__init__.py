from fastapi import APIRouter
from .lidars import router as lidars_router
from .websocket import router as ws_router
from .fusions import router as fusions_router

router = APIRouter()
router.include_router(lidars_router)
router.include_router(ws_router)
router.include_router(fusions_router)
