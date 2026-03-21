from fastapi import APIRouter
from .websocket import router as ws_router
from .system import router as system_router
from .nodes import router as nodes_router
from .edges import router as edges_router
from .config import router as config_router
from .recordings import router as recordings_router
from .logs import router as logs_router
from .calibration import router as calibration_router
from .lidar import router as lidar_router
from .assets import router as assets_router
from .flow_control import router as flow_control_router
from .dag import router as dag_router

router = APIRouter(prefix="/api/v1")
router.include_router(system_router)
router.include_router(nodes_router)
router.include_router(edges_router)
router.include_router(config_router)
router.include_router(recordings_router)
router.include_router(logs_router)
router.include_router(calibration_router)
router.include_router(lidar_router)
router.include_router(assets_router)
router.include_router(flow_control_router)
router.include_router(dag_router)
router.include_router(ws_router)
