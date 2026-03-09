# Object Detection Node Implementation
"""
ML node for 3D bounding box detection using Open3D-ML models like PointPillars.
Outputs original point cloud unchanged plus bounding_boxes metadata.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, List
from .ml_node import MLNode

logger = logging.getLogger(__name__)


class ObjectDetectionNode(MLNode):
    """3D object detection ML node"""
    
    async def process_ml_inference(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process point cloud through object detection model"""
        
        # Extract point cloud from payload
        points = data.get("points")  # Should be (N, 14) numpy array
        if points is None:
            logger.error("No points in data payload")
            return data
            
        # Convert to ml3d input format 
        # Only XYZ needed for detection models
        xyz = points[:, :3].astype(np.float32)
        
        ml_input = {
            "point": xyz,  # (N, 3)
        }
        
        # Run inference via model registry
        if not self.model_registry or not self.loaded_model:
            logger.error("Model registry or loaded model not available")
            return data
            
        result = await self.model_registry.run_inference(
            self.loaded_model.model_key, ml_input
        )
        
        # Extract prediction results
        predict_boxes = result.get("predict_boxes", [])
        
        # Apply confidence filtering
        confidence_threshold = self.config.get("confidence_threshold", 0.5)
        filtered_boxes = [
            box for box in predict_boxes 
            if box.get("confidence", 0.0) >= confidence_threshold
        ]
        
        # Convert to BoundingBox3D format
        bounding_boxes = []
        for box in filtered_boxes:
            bbox = {
                "center_x": float(box["center"][0]),
                "center_y": float(box["center"][1]), 
                "center_z": float(box["center"][2]),
                "size_x": float(box["size"][0]),
                "size_y": float(box["size"][1]),
                "size_z": float(box["size"][2]), 
                "rotation_z": float(box["yaw"]),
                "class_name": box["label_class"],
                "confidence": float(box["confidence"]),
                "class_index": self._get_class_index(box["label_class"]),
                "color": self._get_class_color(box["label_class"])
            }
            bounding_boxes.append(bbox)
        
        # Update payload (points unchanged, add detection metadata)
        result_data = data.copy()
        result_data["bounding_boxes"] = bounding_boxes
        result_data["ml_model_key"] = self.loaded_model.model_key if self.loaded_model else "unknown"
        
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