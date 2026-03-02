from fastapi import APIRouter
from .websocket import router as ws_router
from .system import router as system_router
from .nodes import router as nodes_router
from .edges import router as edges_router
from .config import router as config_router
from .recordings import router as recordings_router
from .logs import router as logs_router
from .calibration import router as calibration_router
from .metrics import router as metrics_router

router = APIRouter(prefix="/api/v1")
router.include_router(system_router)
router.include_router(nodes_router)
router.include_router(edges_router)
router.include_router(config_router)
router.include_router(recordings_router)
router.include_router(logs_router)
router.include_router(calibration_router)
router.include_router(metrics_router)
router.include_router(ws_router)
