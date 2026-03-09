"""
Pydantic models for ML API endpoints

Data schemas for model catalog, status reporting, and WebSocket protocol.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime


class MLModelInfo(BaseModel):
    """Information about an available ML model."""
    model_key: str = Field(..., description="Unique identifier for model + dataset combination")
    model_name: str = Field(..., description="Model architecture name (e.g., RandLANet)")
    dataset_name: str = Field(..., description="Training dataset name (e.g., SemanticKITTI)")
    task: Literal["semantic_segmentation", "object_detection"] = Field(..., description="ML task type")
    num_classes: int = Field(..., description="Number of output classes")
    class_names: List[str] = Field(..., description="Human-readable class labels")
    color_map: List[List[int]] = Field(..., description="RGB color mapping for each class")
    weight_url: str = Field(..., description="Download URL for model weights")
    weight_filename: str = Field(..., description="Local filename for cached weights")
    weight_size_mb: float = Field(..., description="Size of weight file in MB")
    config_file: str = Field(..., description="Path to model configuration file")
    status: str = Field("not_loaded", description="Current loading status")


class MLModelStatus(BaseModel):
    """Runtime status of a loaded ML model."""
    model_key: str = Field(..., description="Model identifier")
    status: Literal["not_loaded", "downloading", "loading", "ready", "error"] = Field(..., description="Current status")
    device: str = Field("N/A", description="Device where model is loaded (cpu, cuda:0, etc)")
    loaded_at: Optional[float] = Field(None, description="Unix timestamp when model became ready")
    weight_cached: bool = Field(False, description="Whether weights are cached locally")
    download_progress_pct: float = Field(0.0, description="Download progress percentage (0-100)")
    inference_count: int = Field(0, description="Total number of inference runs")
    avg_inference_ms: float = Field(0.0, description="Average inference time in milliseconds")
    last_error: Optional[str] = Field(None, description="Most recent error message")


class MLLoadRequest(BaseModel):
    """Request to load a model on specific device."""
    device: str = Field("cpu", description="Target device (cpu, cuda:0, cuda:1, etc)")


class BoundingBox3D(BaseModel):
    """3D bounding box for object detection."""
    id: int = Field(..., description="Unique box identifier within frame")
    label: str = Field(..., description="Object class name")
    label_index: int = Field(..., description="Numeric class index")
    confidence: float = Field(..., description="Detection confidence score")
    center: List[float] = Field(..., description="3D center coordinates [x, y, z]")
    size: List[float] = Field(..., description="3D dimensions [length, width, height]")
    yaw: float = Field(..., description="Rotation around Z-axis in radians")
    color: List[int] = Field(..., description="RGB color for visualization")


class DetectionFrameMetadata(BaseModel):
    """Metadata for object detection WebSocket frames."""
    timestamp: float = Field(..., description="Unix timestamp of frame")
    inference_ms: float = Field(..., description="Inference time in milliseconds")
    boxes: List[BoundingBox3D] = Field(..., description="Detected bounding boxes")
    total_detections: int = Field(..., description="Number of boxes before filtering")
    filtered_detections: int = Field(..., description="Number of boxes after confidence filtering")