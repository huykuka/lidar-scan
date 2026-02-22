from fastapi import APIRouter
from .lidars import router as lidars_router
from .websocket import router as ws_router
from .fusions import router as fusions_router
from .system import router as system_router
from .nodes import router as nodes_router

router = APIRouter(prefix="/api/v1")
router.include_router(system_router)
router.include_router(lidars_router)
router.include_router(ws_router)
router.include_router(fusions_router)
router.include_router(nodes_router)
