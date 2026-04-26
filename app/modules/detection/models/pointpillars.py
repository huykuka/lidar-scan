"""
PointPillars 3D object detection model wrapper.

Wraps the ``pointpillars`` PyTorch package (zhulf0804/PointPillars) behind
the :class:`DetectionModel` interface.  Supports CPU and CUDA inference.

Pretrained KITTI weights detect three classes: Pedestrian, Cyclist, Car.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from app.core.logging import get_logger
from .base import Detection3D, DetectionModel, register_model

logger = get_logger(__name__)

# KITTI class mapping used by the pretrained checkpoint
_KITTI_CLASSES = ["Pedestrian", "Cyclist", "Car"]
_KITTI_LABEL_MAP = {i: name for i, name in enumerate(_KITTI_CLASSES)}

# Default detection range matching KITTI PointPillars config
_DEFAULT_POINT_RANGE = [0.0, -39.68, -3.0, 69.12, 39.68, 1.0]


def _filter_point_range(pts: np.ndarray, point_range: List[float]) -> np.ndarray:
    """Keep only points within the 3D bounding box ``[x1,y1,z1, x2,y2,z2]``."""
    mask = (
        (pts[:, 0] > point_range[0])
        & (pts[:, 1] > point_range[1])
        & (pts[:, 2] > point_range[2])
        & (pts[:, 0] < point_range[3])
        & (pts[:, 1] < point_range[4])
        & (pts[:, 2] < point_range[5])
    )
    return pts[mask]


@register_model(
    "pointpillars",
    display_name="PointPillars (KITTI)",
    description=(
        "Fast voxel-based 3D detector. Pretrained on KITTI dataset "
        "(Car, Pedestrian, Cyclist). ~200ms/frame on CPU."
    ),
)
class PointPillarsModel(DetectionModel):
    """PointPillars wrapper using the ``pointpillars`` PyTorch package."""

    def __init__(self) -> None:
        self._model: Any = None
        self._device_str: str = "cpu"
        self._torch: Any = None
        self._nclasses: int = len(_KITTI_CLASSES)
        self._point_range: List[float] = list(_DEFAULT_POINT_RANGE)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def supported_classes(self) -> List[str]:
        return list(_KITTI_CLASSES)

    def load(self, checkpoint_path: str, device: str = "cpu") -> None:
        """
        Load PointPillars model weights.

        Args:
            checkpoint_path: Path to ``.pth`` file with pretrained weights.
            device: ``"cpu"`` or ``"cuda"``.
        """
        try:
            import torch
            from pointpillars.model import PointPillars as _PointPillarsNet
        except ImportError as exc:
            raise ImportError(
                "PointPillars requires 'torch' and 'pointpillars' packages. "
                "Install with: pip install torch pointpillars"
            ) from exc

        self._torch = torch
        self._device_str = device

        torch_device = torch.device(device)
        self._model = _PointPillarsNet(nclasses=self._nclasses)

        state_dict = torch.load(checkpoint_path, map_location=torch_device, weights_only=True)
        self._model.load_state_dict(state_dict)
        self._model.to(torch_device)
        self._model.eval()

        logger.info(
            "PointPillars loaded from %s on %s (%d classes)",
            checkpoint_path, device, self._nclasses,
        )

    def detect(
        self,
        points: np.ndarray,
        *,
        confidence_threshold: float = 0.3,
        nms_iou_threshold: float = 0.5,
        point_range: Optional[List[float]] = None,
        **kwargs: Any,
    ) -> List[Detection3D]:
        """
        Run inference on a raw point cloud.

        Args:
            points: ``(N, C)`` array — columns 0-2 are ``x, y, z``;
                    column 3 (intensity) is used when present.
            confidence_threshold: Discard detections below this score.
            nms_iou_threshold: BEV IoU threshold for post-hoc NMS.
                               Lower = more aggressive duplicate suppression.
            point_range: ``[x_min, y_min, z_min, x_max, y_max, z_max]``
                         detection volume.  Defaults to KITTI range.

        Returns:
            List of :class:`Detection3D`.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        torch = self._torch
        pc_range = point_range or self._point_range

        # Prepare input: need at least (N, 4) — x, y, z, intensity
        if points.shape[1] < 4:
            pts = np.zeros((points.shape[0], 4), dtype=np.float32)
            pts[:, :points.shape[1]] = points
        else:
            pts = points[:, :4].astype(np.float32)

        # Filter to detection range
        pts = _filter_point_range(pts, pc_range)
        if len(pts) == 0:
            return []

        # Convert to torch tensor
        pc_tensor = torch.from_numpy(pts)
        if self._device_str != "cpu":
            pc_tensor = pc_tensor.to(self._device_str)

        # Run inference
        with torch.no_grad():
            result = self._model(batched_pts=[pc_tensor], mode="test")[0]

        lidar_bboxes = result.get("lidar_bboxes")
        labels = result.get("labels")
        scores = result.get("scores")

        if lidar_bboxes is None or len(lidar_bboxes) == 0:
            return []

        # Convert numpy arrays
        if isinstance(lidar_bboxes, torch.Tensor):
            lidar_bboxes = lidar_bboxes.cpu().numpy()
        if isinstance(labels, torch.Tensor):
            labels = labels.cpu().numpy()
        if isinstance(scores, torch.Tensor):
            scores = scores.cpu().numpy()

        # Filter by confidence
        mask = scores >= confidence_threshold
        lidar_bboxes = lidar_bboxes[mask]
        labels = labels[mask]
        scores = scores[mask]

        if len(lidar_bboxes) == 0:
            return []

        # Apply post-hoc BEV NMS with user-configurable IoU threshold
        from app.modules.detection.utils.nms import nms_3d

        keep = nms_3d(lidar_bboxes, scores, iou_threshold=nms_iou_threshold)
        lidar_bboxes = lidar_bboxes[keep]
        labels = labels[keep]
        scores = scores[keep]

        # Build Detection3D list
        # lidar_bboxes format: (N, 7) → [x, y, z, l, w, h, heading]
        detections: List[Detection3D] = []
        for i in range(len(lidar_bboxes)):
            bbox = lidar_bboxes[i]
            heading = float(bbox[6]) if len(bbox) > 6 else 0.0
            label_idx = int(labels[i])
            detections.append(
                Detection3D(
                    center=[float(bbox[0]), float(bbox[1]), float(bbox[2])],
                    size=[float(bbox[3]), float(bbox[4]), float(bbox[5])],
                    rotation=[0.0, 0.0, heading],
                    label=_KITTI_LABEL_MAP.get(label_idx, f"class_{label_idx}"),
                    score=float(scores[i]),
                )
            )

        return detections
