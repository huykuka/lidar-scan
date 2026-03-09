# ML Node Base Class
"""
Base class for ML nodes providing shared functionality for model management,
torch availability checking, and integration with the DAG system.
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

# Conditional imports for optional torch dependency
try:
    import open3d.ml.torch as ml3d
    TORCH_AVAILABLE = True
except ImportError:
    ml3d = None
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)


class MLNodeStub:
    """Stub class used when torch is not available"""
    
    def __init__(self, node_id: str, config: Dict[str, Any]):
        raise RuntimeError(
            "ML nodes require PyTorch. Please install: pip install -r requirements-ml.txt"
        )


if TORCH_AVAILABLE:
    from app.services.nodes.base_module import ModuleNode
    
    class MLNode(ModuleNode, ABC):
        """Base class for ML nodes with model management"""
        
        def __init__(
            self,
            manager: Any,
            node_id: str,
            op_type: str,
            config: Dict[str, Any],
            name: Optional[str] = None,
            throttle_ms: float = 0  # Handled by NodeManager
        ):
            self.manager = manager
            self.id = node_id
            self.name = name or node_id
            self.op_type = op_type
            self.config = config
            
            self.model_registry = None  # Will be set from MLModelRegistry
            self.loaded_model = None
            self.last_inference_ms = 0.0
            
            # Runtime stats
            self.last_input_at: Optional[float] = None
            self.last_output_at: Optional[float] = None
            self.last_error: Optional[str] = None
            self.processing_time_ms: float = 0.0
            self.input_count: int = 0
            self.output_count: int = 0
            
        async def initialize(self):
            """Initialize ML node and load model"""
            
            # Get model registry singleton
            from .model_registry import MLModelRegistry
            self.model_registry = MLModelRegistry.get_instance()
            
            # Load model based on config
            model_name = self.config.get("model_name")
            dataset_name = self.config.get("dataset_name") 
            device = self.config.get("device", "cpu")
            
            if model_name and dataset_name:
                try:
                    self.loaded_model = await self.model_registry.get_or_load(
                        model_name, dataset_name, device
                    )
                except Exception as e:
                    logger.error(f"Failed to load ML model {model_name}/{dataset_name}: {e}")
        
        def get_status(self, runtime_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            """Override to include ML-specific status"""
            import time
            
            frame_age = time.time() - self.last_output_at if self.last_output_at else None
            status = {
                "id": self.id,
                "name": self.name,
                "type": "ml",
                "op_type": self.op_type,
                "running": True,
                "frame_age_seconds": frame_age,
                "last_input_at": self.last_input_at,
                "last_output_at": self.last_output_at,
                "last_error": self.last_error,
                "processing_time_ms": self.processing_time_ms,
                "input_count": self.input_count,
                "output_count": self.output_count,
            }
            
            if self.loaded_model:
                status.update({
                    "model_name": f"{self.loaded_model.model_name}/{self.loaded_model.dataset_name}",
                    "model_device": self.loaded_model.device,
                    "model_status": self.loaded_model.status.value,
                    "inference_latency_ms": self.last_inference_ms,
                })
            else:
                status.update({
                    "model_name": "Not loaded", 
                    "model_device": "N/A",
                    "model_status": "not_loaded",
                    "inference_latency_ms": 0.0,
                })
                
            return status
        
        @abstractmethod
        async def process_ml_inference(self, data: Dict[str, Any]) -> Dict[str, Any]:
            """Subclasses implement specific ML processing"""
            pass
            
        async def process_data(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            """Main data processing with ML inference"""
            
            # If model not ready, pass through unchanged (warm-up pattern)
            if not self.loaded_model or self.loaded_model.status.value != "ready":
                logger.debug(f"ML model not ready, passing through data unchanged")
                return data
                
            # Run ML inference
            start_time = asyncio.get_event_loop().time()
            try:
                result = await self.process_ml_inference(data)
                self.last_inference_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                return result
            except Exception as e:
                logger.error(f"ML inference failed: {e}")
                # Fallback to pass-through on error
                return data
                
        async def on_input(self, payload: Dict[str, Any]) -> None:
            """Handle input data and forward processed results"""
            import time
            
            self.last_input_at = time.time()
            start_time = time.time()
            
            points = payload.get("points")
            if points is None or len(points) == 0:
                return

            self.input_count = len(points) if hasattr(points, '__len__') else 1
            
            try:
                # Process with ML inference
                processed_data = await self.process_data(payload)
                
                if processed_data is not None:
                    self.output_count = len(processed_data.get("points", [])) if processed_data.get("points") is not None else 0
                    self.processing_time_ms = (time.time() - start_time) * 1000
                    self.last_output_at = time.time()
                    self.last_error = None

                    # Forward to downstream nodes
                    await self.manager.forward_data(self.id, processed_data)

            except Exception as e:
                self.last_error = str(e)
                logger.error(f"[{self.id}] Error processing ML data: {e}", exc_info=True)

else:
    # When torch not available, MLNode is just the stub
    MLNode = MLNodeStub