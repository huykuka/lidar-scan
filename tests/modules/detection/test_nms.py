"""Unit tests for 3D NMS utility."""
import numpy as np
import pytest

from app.modules.detection.utils.nms import nms_3d


class TestNms3d:
    def test_empty_input(self):
        boxes = np.zeros((0, 7), dtype=np.float32)
        scores = np.array([], dtype=np.float32)
        keep = nms_3d(boxes, scores)
        assert len(keep) == 0

    def test_single_box(self):
        boxes = np.array([[0, 0, 0, 2, 2, 1, 0]], dtype=np.float32)
        scores = np.array([0.9], dtype=np.float32)
        keep = nms_3d(boxes, scores)
        assert list(keep) == [0]

    def test_no_overlap(self):
        boxes = np.array([
            [0, 0, 0, 1, 1, 1, 0],
            [10, 10, 0, 1, 1, 1, 0],
        ], dtype=np.float32)
        scores = np.array([0.9, 0.8], dtype=np.float32)
        keep = nms_3d(boxes, scores, iou_threshold=0.5)
        assert len(keep) == 2

    def test_full_overlap_suppresses_lower(self):
        boxes = np.array([
            [0, 0, 0, 2, 2, 1, 0],
            [0, 0, 0, 2, 2, 1, 0],  # identical box
        ], dtype=np.float32)
        scores = np.array([0.9, 0.5], dtype=np.float32)
        keep = nms_3d(boxes, scores, iou_threshold=0.5)
        assert len(keep) == 1
        assert keep[0] == 0  # higher score kept

    def test_partial_overlap(self):
        boxes = np.array([
            [0, 0, 0, 4, 4, 1, 0],
            [1, 1, 0, 4, 4, 1, 0],  # significant overlap
        ], dtype=np.float32)
        scores = np.array([0.9, 0.8], dtype=np.float32)
        # With high threshold, both kept
        keep_high = nms_3d(boxes, scores, iou_threshold=0.99)
        assert len(keep_high) == 2
        # With low threshold, one suppressed
        keep_low = nms_3d(boxes, scores, iou_threshold=0.1)
        assert len(keep_low) == 1

    def test_score_ordering(self):
        boxes = np.array([
            [0, 0, 0, 2, 2, 1, 0],
            [0, 0, 0, 2, 2, 1, 0],
            [0, 0, 0, 2, 2, 1, 0],
        ], dtype=np.float32)
        scores = np.array([0.3, 0.9, 0.5], dtype=np.float32)
        keep = nms_3d(boxes, scores, iou_threshold=0.5)
        assert keep[0] == 1  # highest score first
