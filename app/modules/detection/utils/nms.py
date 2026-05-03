"""
Axis-aligned 3D Non-Maximum Suppression (NMS) for bounding boxes.

Operates on BEV (Bird's Eye View) IoU — ignores height overlap — which is
the standard approach for LiDAR-based 3D object detection.
"""
from __future__ import annotations

import numpy as np


def _bev_iou_matrix(boxes: np.ndarray) -> np.ndarray:
    """
    Compute pairwise BEV IoU for axis-aligned 3D boxes.

    Args:
        boxes: ``(N, 7)`` array with columns
               ``[x, y, z, length, width, height, heading]``.
               Only ``x, y, length, width`` are used for BEV IoU.

    Returns:
        ``(N, N)`` IoU matrix.
    """
    x = boxes[:, 0]
    y = boxes[:, 1]
    l = boxes[:, 3]  # noqa: E741
    w = boxes[:, 4]

    x1 = x - l / 2
    x2 = x + l / 2
    y1 = y - w / 2
    y2 = y + w / 2

    area = l * w

    # Broadcast pairwise intersection
    inter_x1 = np.maximum(x1[:, None], x1[None, :])
    inter_y1 = np.maximum(y1[:, None], y1[None, :])
    inter_x2 = np.minimum(x2[:, None], x2[None, :])
    inter_y2 = np.minimum(y2[:, None], y2[None, :])

    inter_w = np.maximum(0, inter_x2 - inter_x1)
    inter_h = np.maximum(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    union_area = area[:, None] + area[None, :] - inter_area
    iou = np.where(union_area > 0, inter_area / union_area, 0.0)
    return iou


def nms_3d(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float = 0.5,
) -> np.ndarray:
    """
    Greedy NMS on 3D boxes using BEV IoU.

    Args:
        boxes:  ``(N, 7)`` — ``[x, y, z, length, width, height, heading]``.
        scores: ``(N,)`` confidence scores.
        iou_threshold: Suppress boxes with BEV IoU above this value.

    Returns:
        ``(K,)`` integer array of kept indices, sorted by descending score.
    """
    if len(boxes) == 0:
        return np.array([], dtype=np.int64)

    order = np.argsort(-scores)
    iou = _bev_iou_matrix(boxes)

    keep: list[int] = []
    suppressed = np.zeros(len(boxes), dtype=bool)

    for idx in order:
        if suppressed[idx]:
            continue
        keep.append(idx)
        suppressed |= iou[idx] > iou_threshold
        suppressed[idx] = False  # keep current box

    return np.array(keep, dtype=np.int64)
