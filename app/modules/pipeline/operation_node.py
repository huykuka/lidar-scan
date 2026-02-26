from typing import Any, Dict, Optional
import time
import numpy as np
from app.core.logging_config import get_logger
from app.modules.pipeline.factory import OperationFactory
from app.services.nodes.base_module import ModuleNode

logger = get_logger(__name__)

class OperationNode(ModuleNode):
    """
    A node that performs a single point cloud operation (e.g., Filtering, Downsampling).
    """
    def __init__(
        self,
        manager: Any,
        node_id: str,
        op_type: str,
        op_config: Dict[str, Any],
        name: Optional[str] = None
    ):
        self.manager = manager
        self.id = node_id
        self.name = name or node_id
        self.op_type = op_type
        
        # Instantiate the operation
        try:
            self.op = OperationFactory.create(op_type, op_config)
        except Exception as e:
            logger.error(f"[{self.id}] Failed to create operation '{op_type}': {e}")
            raise

        # Runtime stats
        self.last_input_at: Optional[float] = None
        self.last_output_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.processing_time_ms: float = 0.0
        self.input_count: int = 0
        self.output_count: int = 0

    async def on_input(self, payload: Dict[str, Any]):
        """Receives data, processes it, and forwards to downstream."""
        from app.modules.pipeline.base import PointConverter
        
        self.last_input_at = time.time()
        start_time = time.time()
        
        points = payload.get("points")
        if points is None or len(points) == 0:
            return

        self.input_count = len(points)
        
        try:
            # Move heavy CPU-bound Point Cloud operations to a background thread
            # so they don't block the main FastAPI/Websocket async event loop.
            def _sync_compute():
                # 1. Convert numpy -> Open3D t.PointCloud
                pcd_in = PointConverter.to_pcd(points)
                # 2. Apply the atomic operation
                outcome = self.op.apply(pcd_in)
                # Handle both (pcd, metadata) and raw pcd returns
                if isinstance(outcome, tuple):
                    pcd_out, op_result = outcome
                else:
                    pcd_out, op_result = outcome, {}
                # 3. Convert back to numpy for downstream
                return PointConverter.to_points(pcd_out)
                
            import asyncio
            
            # Open3D OpenGL contexts MUST strictly execute on the main thread
            # Background threading causes GTK / Wayland context explosions
            if self.op_type == "visualize":
                processed_points = _sync_compute()
            else:
                processed_points = await asyncio.to_thread(_sync_compute)
            
            if processed_points is None or len(processed_points) == 0:
                 return

            self.output_count = len(processed_points)
            self.processing_time_ms = (time.time() - start_time) * 1000
            self.last_output_at = time.time()
            self.last_error = None

            # Prepare payload for downstream
            new_payload = payload.copy()
            new_payload["points"] = processed_points
            new_payload["node_id"] = self.id
            new_payload["processed_by"] = self.id
            
            # Forward to downstream nodes via Manager
            # NodeManager will handle WebSocket broadcasting automatically
            await self.manager.forward_data(self.id, new_payload)

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"[{self.id}] Error processing data: {e}", exc_info=True)

    def get_status(self, runtime_status: Dict[str, Any]) -> Dict[str, Any]:
        """Returns standard status for this node"""
        frame_age = time.time() - self.last_output_at if self.last_output_at else None
        # Auto-generate topic from node name and ID
        topic = f"{self.name}_{self.id[:8]}"
        return {
            "id": self.id,
            "name": self.name,
            "type": "operation",
            "op_type": self.op_type,
            "running": True,
            "frame_age_seconds": frame_age,
            "last_input_at": self.last_input_at,
            "last_output_at": self.last_output_at,
            "last_error": self.last_error,
            "processing_time_ms": self.processing_time_ms,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "topic": topic
        }
