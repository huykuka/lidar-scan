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
        _lock = asyncio.Lock()  # Class-level lock for singleton thread safety
        MAX_LOADED_MODELS = 2  # LRU eviction limit
        
        def __init__(self):
            self.models: Dict[str, LoadedModel] = {}
            self.models_dir = os.getenv("ML_MODELS_DIR", "./models")
            self.access_order: List[str] = []  # Track access for LRU
            self._instance_lock = asyncio.Lock()  # Instance-level operations lock
            os.makedirs(self.models_dir, exist_ok=True)
            
        @classmethod
        async def get_instance(cls) -> "MLModelRegistry":
            """Get singleton instance with thread safety"""
            async with cls._lock:
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
            """Get existing model or load new one with LRU eviction (thread-safe)"""
            
            async with self._instance_lock:
                model_key = self._make_model_key(model_name, dataset_name)
                
                # Return existing if already loaded
                if model_key in self.models:
                    existing = self.models[model_key]
                    self._update_access_order(model_key)  # Update LRU tracking
                    
                    if existing.status == ModelStatus.READY:
                        return existing
                    elif existing.status in [ModelStatus.DOWNLOADING, ModelStatus.LOADING]:
                        # Wait for loading to complete (release lock temporarily)
                        pass  # Will wait outside the lock
                
                # Check if we need to evict models for memory management
                await self._ensure_capacity_for_new_model()
                        
                # Create new model entry
                loaded_model = LoadedModel(
                    model_key=model_key,
                    model_name=model_name,
                    dataset_name=dataset_name,
                    device=device,
                    status=ModelStatus.DOWNLOADING
                )
                self.models[model_key] = loaded_model
                self._update_access_order(model_key)
                
                # Start loading process
                asyncio.create_task(self._load_model_async(loaded_model))
                
                return loaded_model
            
        def _update_access_order(self, model_key: str) -> None:
            """Update LRU access order"""
            if model_key in self.access_order:
                self.access_order.remove(model_key)
            self.access_order.append(model_key)
            
        async def _ensure_capacity_for_new_model(self) -> None:
            """Evict oldest models if at capacity limit"""
            ready_models = [
                key for key, model in self.models.items() 
                if model.status == ModelStatus.READY
            ]
            
            if len(ready_models) >= self.MAX_LOADED_MODELS:
                # Evict oldest ready model
                for model_key in self.access_order:
                    if model_key in ready_models:
                        await self._unload_model(model_key)
                        logger.info(f"Evicted model {model_key} for capacity management")
                        break
                        
        async def _unload_model(self, model_key: str) -> None:
            """Unload a specific model to free memory (thread-safe)"""
            async with self._instance_lock:
                if model_key in self.models:
                    model = self.models[model_key]
                    
                    # Clean up pipeline resources if available
                    if hasattr(model.pipeline, 'cleanup'):
                        await asyncio.to_thread(model.pipeline.cleanup)
                    
                    # Remove from registry
                    del self.models[model_key]
                    
                    # Remove from access tracking
                    if model_key in self.access_order:
                        self.access_order.remove(model_key)
                        
                    logger.info(f"Unloaded model {model_key}")
                
        def unload_model_sync(self, model_key: str) -> bool:
            """Synchronous model unloading for API endpoints (thread-safe)"""
            # Use a simple synchronous approach with basic locking
            if model_key not in self.models:
                return False
                
            model = self.models[model_key]
            
            # Basic cleanup - no async cleanup for simplicity
            del self.models[model_key]
            
            if model_key in self.access_order:
                self.access_order.remove(model_key)
                
            logger.info(f"Synchronously unloaded model {model_key}")
            return True
            
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
            weight_filename = f"{loaded_model.model_key.lower()}.pth"
            weight_path = os.path.join(self.models_dir, weight_filename)
            
            if not os.path.exists(weight_path):
                logger.info(f"Downloading weights for {loaded_model.model_key}")
                
                # Run download in thread pool to avoid blocking async event loop
                await asyncio.to_thread(self._download_weights, loaded_model, weight_path)
                    
            return weight_path
            
        def _download_weights(self, loaded_model: LoadedModel, weight_path: str) -> None:
            """Download model weights (runs in thread pool)"""
            try:
                # Mock download - in real implementation would use urllib.request.urlretrieve
                # or requests with progress callback
                import time
                time.sleep(1.0)  # Simulate download time
                
                # Create mock weight file
                with open(weight_path, 'w') as f:
                    f.write(f"# Mock weight file for {loaded_model.model_key}\n")
                    f.write(f"# Model: {loaded_model.model_name}\n")
                    f.write(f"# Dataset: {loaded_model.dataset_name}\n")
                    
                logger.info(f"Downloaded weights to {weight_path}")
                
            except Exception as e:
                logger.error(f"Failed to download weights for {loaded_model.model_key}: {e}")
                raise
            
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