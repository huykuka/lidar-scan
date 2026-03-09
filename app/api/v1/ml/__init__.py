"""
ML API Router Module

REST endpoints for managing Open3D-ML models and monitoring inference status.
Provides model catalog, loading/unloading, and real-time status information.
"""

from fastapi import APIRouter, HTTPException, status
from typing import List, Dict, Any
import logging

# Conditional imports for ML dependencies
try:
    from app.modules.ml.model_registry import MLModelRegistry, ModelStatus
    ML_AVAILABLE = True
except ImportError:
    MLModelRegistry = None
    ModelStatus = None
    ML_AVAILABLE = False

from .schemas import MLModelInfo, MLModelStatus, MLLoadRequest, BoundingBox3D

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ml", tags=["Machine Learning"])

# Hardcoded model catalog as per api-spec.md
PREDEFINED_MODELS = [
    MLModelInfo(
        model_key="randlanet_semantickitti",
        model_name="RandLANet", 
        dataset_name="SemanticKITTI",
        task="semantic_segmentation",
        num_classes=19,
        class_names=[
            "unlabeled", "car", "bicycle", "motorcycle", "truck", "other-vehicle",
            "person", "bicyclist", "motorcyclist", "road", "parking", "sidewalk", 
            "other-ground", "building", "fence", "vegetation", "trunk", "terrain", "pole"
        ],
        color_map=[
            [0, 0, 0], [245, 150, 100], [245, 230, 100], [150, 60, 30], [180, 30, 80], [255, 0, 0],
            [30, 30, 255], [200, 40, 255], [90, 30, 150], [255, 0, 255], [255, 150, 255], [75, 0, 75],
            [75, 0, 175], [0, 200, 255], [50, 120, 255], [0, 175, 0], [0, 60, 135], [80, 240, 150], [150, 240, 255]
        ],
        weight_url="https://storage.googleapis.com/open3d-ml-models/randlanet_semantickitti.pth",
        weight_filename="randlanet_semantickitti.pth",
        weight_size_mb=52.4,
        config_file="configs/randlanet_semantickitti.yml",
        status="not_loaded"
    ),
    MLModelInfo(
        model_key="kpfcnn_semantickitti", 
        model_name="KPFCNN",
        dataset_name="SemanticKITTI", 
        task="semantic_segmentation",
        num_classes=19,
        class_names=[
            "unlabeled", "car", "bicycle", "motorcycle", "truck", "other-vehicle",
            "person", "bicyclist", "motorcyclist", "road", "parking", "sidewalk",
            "other-ground", "building", "fence", "vegetation", "trunk", "terrain", "pole"
        ],
        color_map=[
            [0, 0, 0], [245, 150, 100], [245, 230, 100], [150, 60, 30], [180, 30, 80], [255, 0, 0],
            [30, 30, 255], [200, 40, 255], [90, 30, 150], [255, 0, 255], [255, 150, 255], [75, 0, 75],
            [75, 0, 175], [0, 200, 255], [50, 120, 255], [0, 175, 0], [0, 60, 135], [80, 240, 150], [150, 240, 255]
        ],
        weight_url="https://storage.googleapis.com/open3d-ml-models/kpfcnn_semantickitti.pth",
        weight_filename="kpfcnn_semantickitti.pth", 
        weight_size_mb=67.8,
        config_file="configs/kpfcnn_semantickitti.yml",
        status="not_loaded"
    ),
    MLModelInfo(
        model_key="pointpillars_kitti",
        model_name="PointPillars",
        dataset_name="KITTI", 
        task="object_detection",
        num_classes=3,
        class_names=["car", "pedestrian", "cyclist"],
        color_map=[[255, 80, 80], [80, 255, 80], [80, 80, 255]],
        weight_url="https://storage.googleapis.com/open3d-ml-models/pointpillars_kitti.pth",
        weight_filename="pointpillars_kitti.pth",
        weight_size_mb=34.2, 
        config_file="configs/pointpillars_kitti.yml",
        status="not_loaded"
    ),
    MLModelInfo(
        model_key="pointrcnn_kitti",
        model_name="PointRCNN", 
        dataset_name="KITTI",
        task="object_detection",
        num_classes=3, 
        class_names=["car", "pedestrian", "cyclist"],
        color_map=[[255, 80, 80], [80, 255, 80], [80, 80, 255]],
        weight_url="https://storage.googleapis.com/open3d-ml-models/pointrcnn_kitti.pth", 
        weight_filename="pointrcnn_kitti.pth",
        weight_size_mb=89.1,
        config_file="configs/pointrcnn_kitti.yml",
        status="not_loaded"
    )
]


@router.get("/models", response_model=List[MLModelInfo])
async def get_models():
    """
    Get list of available ML models.
    
    Returns hardcoded model catalog with current loading status.
    """
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML functionality requires PyTorch. Install: pip install -r requirements-ml.txt"
        )
    
    try:
        registry = await MLModelRegistry.get_instance()
        
        # Update status from registry
        models = []
        for model in PREDEFINED_MODELS:
            model_copy = model.dict()
            
            # Check if model is loaded in registry
            registry_status = registry.get_model_status(model.model_key)
            model_copy["status"] = registry_status.get("status", "not_loaded")
            
            models.append(MLModelInfo(**model_copy))
            
        return models
        
    except Exception as e:
        logger.error(f"Error getting model list: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve model catalog"
        )


@router.get("/models/{model_key}/status", response_model=MLModelStatus)
async def get_model_status(model_key: str):
    """
    Get detailed status of a specific model.
    """
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML functionality requires PyTorch. Install: pip install -r requirements-ml.txt"
        )
    
    # Validate model_key exists in catalog
    model_info = next((m for m in PREDEFINED_MODELS if m.model_key == model_key), None)
    if not model_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_key}' not found in catalog"
        )
    
    try:
        registry = await MLModelRegistry.get_instance()
        status_info = registry.get_model_status(model_key)
        
        return MLModelStatus(
            model_key=model_key,
            status=status_info.get("status", "not_loaded"),
            device=status_info.get("device", "N/A"),
            loaded_at=status_info.get("loaded_at"),
            weight_cached=False,  # TODO: Implement cache checking
            download_progress_pct=0.0,  # TODO: Implement progress tracking
            inference_count=status_info.get("inference_count", 0),
            avg_inference_ms=status_info.get("avg_inference_ms", 0.0),
            last_error=status_info.get("last_error")
        )
        
    except Exception as e:
        logger.error(f"Error getting model status for {model_key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get model status"
        )


@router.post("/models/{model_key}/load", status_code=status.HTTP_202_ACCEPTED)
async def load_model(model_key: str, request: MLLoadRequest):
    """
    Initiate model loading in background.
    
    Returns 202 Accepted - model loading happens asynchronously.
    """
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML functionality requires PyTorch. Install: pip install -r requirements-ml.txt"
        )
    
    # Validate model_key exists in catalog
    model_info = next((m for m in PREDEFINED_MODELS if m.model_key == model_key), None)
    if not model_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_key}' not found in catalog"
        )
    
    try:
        registry = await MLModelRegistry.get_instance()
        
        # Check if already loaded
        current_status = registry.get_model_status(model_key)
        if current_status.get("status") == "ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Model '{model_key}' is already loaded"
            )
        
        # Start loading process
        await registry.get_or_load(
            model_info.model_name, 
            model_info.dataset_name, 
            request.device
        )
        
        return {
            "message": f"Model '{model_key}' loading initiated", 
            "device": request.device
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading model {model_key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate model loading"
        )


@router.delete("/models/{model_key}", status_code=status.HTTP_200_OK)
async def unload_model(model_key: str):
    """
    Unload a currently loaded model to free memory.
    """
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML functionality requires PyTorch. Install: pip install -r requirements-ml.txt"
        )
    
    # Validate model_key exists in catalog
    model_info = next((m for m in PREDEFINED_MODELS if m.model_key == model_key), None)
    if not model_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_key}' not found in catalog"
        )
    
    try:
        registry = await MLModelRegistry.get_instance()
        
        # Check if model is loaded
        current_status = registry.get_model_status(model_key)
        if current_status.get("status") == "not_loaded":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model '{model_key}' is not currently loaded"
            )
        
        # TODO: Use proper model unloading method
        success = registry.unload_model_sync(model_key)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model '{model_key}' is not currently loaded"
            )
        
        return {"message": f"Model '{model_key}' unloaded successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unloading model {model_key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unload model"
        )