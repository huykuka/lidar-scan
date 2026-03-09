# Semantic Segmentation Node Implementation
"""
ML node for per-point semantic segmentation using Open3D-ML models like RandLA-Net.
Outputs augmented point clouds with semantic_label as 15th column.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional

try:
    import open3d.ml.torch as ml3d
    TORCH_AVAILABLE = True
except ImportError:
    ml3d = None
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)

if TORCH_AVAILABLE:
    from .ml_node import MLNode
    
    class SemanticSegmentationNode(MLNode):
        """Semantic segmentation ML node"""
        
        async def process_ml_inference(self, data: Dict[str, Any]) -> Dict[str, Any]:
            """Process point cloud through semantic segmentation model"""
            
            # Extract point cloud from payload
            points = data.get("points")  # Should be (N, 14) numpy array
            if points is None:
                logger.error("No points in data payload")
                return data
                
            # Convert to ml3d input format
            # Extract XYZ (columns 0-2) and intensity (column 13 per FIELD_MAP)
            xyz = points[:, :3].astype(np.float32)
            intensity = points[:, 13:14].astype(np.float32)  # Column 13 is intensity
            
            ml_input = {
                "point": xyz,  # (N, 3)
                "feat": intensity  # (N, 1) 
            }
            
            # Run inference via model registry
            if not self.model_registry or not self.loaded_model:
                logger.error("Model registry or loaded model not available")
                return data
                
            result = await self.model_registry.run_inference(
                self.loaded_model.model_key, ml_input
            )
            
            # Extract prediction results
            predict_labels = result.get("predict_labels")  # (N,) int32
            predict_scores = result.get("predict_scores")  # (N, C) float32
            
            if predict_labels is None:
                logger.error("No predict_labels in ML inference result")
                return data
                
            # Augment original point cloud with semantic labels
            # Add as 15th column (index 14)
            labels_float = predict_labels.astype(np.float32)  # Cast to maintain schema
            augmented_cloud = np.column_stack([points, labels_float])  # (N, 15)
            
            # Update payload
            result_data = data.copy()
            result_data["points"] = augmented_cloud
            result_data["ml_labels"] = predict_labels
            result_data["ml_scores"] = predict_scores
            result_data["ml_num_classes"] = predict_scores.shape[1] if predict_scores is not None else 0
            
            return result_data

else:
    from .ml_node import MLNodeStub as SemanticSegmentationNode