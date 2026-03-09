# Object Detection Node Implementation
"""
ML node for 3D bounding box detection using Open3D-ML models like PointPillars.
Outputs original point cloud unchanged plus bounding_boxes metadata.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, List

try:
    import open3d.ml.torch as ml3d
    TORCH_AVAILABLE = True
except ImportError:
    ml3d = None
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)

if TORCH_AVAILABLE:
    from .ml_node import MLNode
    
    class ObjectDetectionNode(MLNode):
        """3D object detection ML node"""
        
        async def process_ml_inference(self, data: Dict[str, Any]) -> Dict[str, Any]:
            """Process point cloud through object detection model"""
            
            # Extract point cloud from 14-column numpy array
            point_cloud = data.get("point_cloud") 
            if point_cloud is None:
                logger.error("No point_cloud in data payload")
                return data
                
            # Convert to ml3d input format  
            # Extract only XYZ (columns 0-2) for object detection
            xyz = point_cloud[:, :3].astype(np.float32)
            
            ml_input = {
                "point": xyz,  # (N, 3)
            }
            
            # Run inference via model registry
            result = await self.model_registry.run_inference(
                self.loaded_model.model_key, ml_input
            )
            
            # Extract bounding box predictions
            predict_boxes = result.get("predict_boxes", [])
            
            # Filter by confidence threshold
            confidence_threshold = self.config.get("confidence_threshold", 0.5)
            filtered_boxes = [
                box for box in predict_boxes 
                if box.get("confidence", 0.0) >= confidence_threshold
            ]
            
            # Convert to BoundingBox3D format with color mapping
            bounding_boxes = []
            for i, box in enumerate(filtered_boxes):
                bbox = {
                    "id": i,
                    "label": box.get("label_class", "unknown"),
                    "label_index": self._get_class_index(box.get("label_class", "unknown")),
                    "confidence": box.get("confidence", 0.0),
                    "center": box.get("center", [0.0, 0.0, 0.0]),
                    "size": box.get("size", [1.0, 1.0, 1.0]),
                    "yaw": box.get("yaw", 0.0),
                    "color": self._get_class_color(box.get("label_class", "unknown"))
                }
                bounding_boxes.append(bbox)
            
            # Return original point cloud unchanged + detection metadata
            result_data = data.copy()
            result_data["bounding_boxes"] = bounding_boxes
            
            logger.debug(f"Detected {len(bounding_boxes)} objects after confidence filtering")
            
            return result_data
            
        def _get_class_index(self, class_name: str) -> int:
            """Map class name to index (KITTI classes)"""
            class_map = {"car": 0, "pedestrian": 1, "cyclist": 2}
            return class_map.get(class_name.lower(), 0)
            
        def _get_class_color(self, class_name: str) -> List[int]:
            """Map class name to RGB color (KITTI color scheme)"""
            color_map = {
                "car": [255, 80, 80],
                "pedestrian": [80, 255, 80], 
                "cyclist": [80, 80, 255]
            }
            return color_map.get(class_name.lower(), [128, 128, 128])

else:
    from .ml_node import MLNodeStub as ObjectDetectionNode