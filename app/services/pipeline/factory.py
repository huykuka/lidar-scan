from typing import Any, Dict, Type
from app.services.pipeline.base import PipelineOperation
from app.services.pipeline.operations import (
    Crop,
    Downsample,
    UniformDownsample,
    StatisticalOutlierRemoval,
    RadiusOutlierRemoval,
    PlaneSegmentation,
    Clustering,
    Filter,
    FilterByKey,
    BoundaryDetection,
    DebugSave,
    SaveDataStructure
)
_OP_MAP: Dict[str, Type[PipelineOperation]] = {
    "crop": Crop,
    "downsample": Downsample,
    "uniform_downsample": UniformDownsample,
    "statistical_outlier_removal": StatisticalOutlierRemoval,
    "outlier_removal": StatisticalOutlierRemoval,  # Alias for node registry and UI
    "radius_outlier_removal": RadiusOutlierRemoval,
    "plane_segmentation": PlaneSegmentation,
    "clustering": Clustering,
    "filter": Filter,
    "filter_by_key": FilterByKey,
    "boundary_detection": BoundaryDetection,
    "debug_save": DebugSave,
    "save_structure": SaveDataStructure
}

class OperationFactory:
    @staticmethod
    def create(op_type: str, config: Dict[str, Any]) -> PipelineOperation:
        if op_type not in _OP_MAP:
            raise ValueError(f"Unknown operation type: '{op_type}'. Available: {list(_OP_MAP.keys())}")
        
        op_class = _OP_MAP[op_type]
        return op_class(**config)
