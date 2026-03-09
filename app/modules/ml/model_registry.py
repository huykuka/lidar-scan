# ML Model Registry - Singleton Service
"""
Singleton service for managing Open3D-ML model instances.
Handles model loading, caching, and inference execution.
"""

import logging
import asyncio
import urllib.request
import os
import numpy as np
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

try:
    import open3d.ml.torch as ml3d
    TORCH_AVAILABLE = True
except ImportError:
    ml3d = None  
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    NOT_LOADED = "not_loaded"
    DOWNLOADING = "downloading" 
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


@dataclass
class LoadedModel:
    """Represents a loaded ML model instance"""
    model_key: str
    model_name: str
    dataset_name: str
    device: str
    status: ModelStatus
    pipeline: Any = None  # ml3d.pipelines instance
    loaded_at: Optional[float] = None
    error_message: Optional[str] = None
    inference_count: int = 0
    total_inference_ms: float = 0.0


if TORCH_AVAILABLE:
    
    class MLModelRegistry:
        """Singleton registry for ML model management"""
        
        _instance: Optional["MLModelRegistry"] = None
        
        def __init__(self):
            self.models: Dict[str, LoadedModel] = {}
            self.models_dir = os.getenv("ML_MODELS_DIR", "./models")
            os.makedirs(self.models_dir, exist_ok=True)
            
        @classmethod
        def get_instance(cls) -> "MLModelRegistry":
            """Get singleton instance"""
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
            
        def _make_model_key(self, model_name: str, dataset_name: str) -> str:
            """Generate model key from name and dataset"""
            return f"{model_name}__{dataset_name}"
            
        async def get_or_load(
            self, 
            model_name: str, 
            dataset_name: str, 
            device: str = "cpu"
        ) -> LoadedModel:
            """Get existing model or load new one"""
            
            model_key = self._make_model_key(model_name, dataset_name)
            
            # Return existing if already loaded
            if model_key in self.models:
                existing = self.models[model_key]
                if existing.status == ModelStatus.READY:
                    return existing
                elif existing.status in [ModelStatus.DOWNLOADING, ModelStatus.LOADING]:
                    # Wait for loading to complete
                    while existing.status in [ModelStatus.DOWNLOADING, ModelStatus.LOADING]:
                        await asyncio.sleep(0.1)
                    return existing
                    
            # Create new model entry
            loaded_model = LoadedModel(
                model_key=model_key,
                model_name=model_name,
                dataset_name=dataset_name,
                device=device,
                status=ModelStatus.DOWNLOADING
            )
            self.models[model_key] = loaded_model
            
            # Start loading process
            asyncio.create_task(self._load_model_async(loaded_model))
            
            return loaded_model
            
        async def _load_model_async(self, loaded_model: LoadedModel):
            """Async model loading process"""
            try:
                # Download weights if needed
                weight_path = await self._ensure_weights_downloaded(loaded_model)
                
                # Load model  
                loaded_model.status = ModelStatus.LOADING
                pipeline = await asyncio.to_thread(self._load_pipeline, loaded_model, weight_path)
                
                # Update model state
                loaded_model.pipeline = pipeline
                loaded_model.status = ModelStatus.READY
                loaded_model.loaded_at = asyncio.get_event_loop().time()
                
                logger.info(f"Successfully loaded {loaded_model.model_key}")
                
            except Exception as e:
                loaded_model.status = ModelStatus.ERROR
                loaded_model.error_message = str(e)
                logger.error(f"Failed to load {loaded_model.model_key}: {e}")
                
        async def _ensure_weights_downloaded(self, loaded_model: LoadedModel) -> str:
            """Ensure model weights are cached locally"""
            # This would implement actual weight downloading
            # For now, return placeholder path
            weight_filename = f"{loaded_model.model_key.lower()}.pth"
            weight_path = os.path.join(self.models_dir, weight_filename)
            
            if not os.path.exists(weight_path):
                # Mock download - in real implementation would download from URL
                logger.info(f"Mock downloading weights for {loaded_model.model_key}")
                await asyncio.sleep(1.0)  # Simulate download time
                
                # Create empty file as placeholder
                with open(weight_path, 'w') as f:
                    f.write("# Mock weight file\n")
                    
            return weight_path
            
        def _load_pipeline(self, loaded_model: LoadedModel, weight_path: str):
            """Load ml3d pipeline (runs in thread pool)"""
            # This would implement actual pipeline loading
            # For now, return mock pipeline object
            logger.info(f"Mock loading pipeline for {loaded_model.model_key}")
            
            class MockPipeline:
                def run_inference(self, data):
                    # Mock inference results
                    N = data["point"].shape[0] 
                    if "semantic" in loaded_model.model_name.lower():
                        return {
                            "predict_labels": np.random.randint(0, 19, size=N, dtype=np.int32),
                            "predict_scores": np.random.random((N, 19)).astype(np.float32)
                        }
                    else:  # object detection
                        return {
                            "predict_boxes": [
                                {
                                    "center": [1.0, 0.0, 0.0],
                                    "size": [4.0, 2.0, 1.5], 
                                    "yaw": 0.1,
                                    "label_class": "car",
                                    "confidence": 0.85
                                }
                            ]
                        }
                        
            return MockPipeline()
            
        async def run_inference(self, model_key: str, data: Dict[str, Any]) -> Dict[str, Any]:
            """Run inference on loaded model"""
            if model_key not in self.models:
                raise ValueError(f"Model {model_key} not loaded")
                
            loaded_model = self.models[model_key]
            if loaded_model.status != ModelStatus.READY:
                raise RuntimeError(f"Model {model_key} not ready (status: {loaded_model.status})")
                
            # Run inference in thread pool
            start_time = asyncio.get_event_loop().time()
            result = await asyncio.to_thread(loaded_model.pipeline.run_inference, data)
            inference_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # Update metrics
            loaded_model.inference_count += 1
            loaded_model.total_inference_ms += inference_time
            
            return result
            
        def get_model_status(self, model_key: str) -> Dict[str, Any]:
            """Get status of a specific model"""
            if model_key not in self.models:
                return {"model_key": model_key, "status": "not_loaded"}
                
            model = self.models[model_key]
            avg_inference = (
                model.total_inference_ms / model.inference_count 
                if model.inference_count > 0 else 0.0
            )
            
            return {
                "model_key": model_key,
                "status": model.status.value,
                "device": model.device,
                "loaded_at": model.loaded_at,
                "inference_count": model.inference_count,
                "avg_inference_ms": avg_inference,
                "last_error": model.error_message
            }

else:
    # Stub when torch not available
    class MLModelRegistry:
        @classmethod
        def get_instance(cls):
            raise RuntimeError("ML model registry requires PyTorch. Install requirements-ml.txt")