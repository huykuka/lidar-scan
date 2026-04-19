"""
Unit tests for ShapeTracker — spatial IoU-based shape ID stabilization.

TDD: these tests are written BEFORE the implementation.
"""

from __future__ import annotations

import pytest

from app.services.nodes.shape_tracker import ShapeTracker, aabb_iou


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _cube(center, size, node_name="node_a"):
    return {
        "type": "cube",
        "node_name": node_name,
        "center": center,
        "size": size,
        "rotation": [0.0, 0.0, 0.0],
        "color": "#00ff00",
        "opacity": 0.4,
        "wireframe": True,
        "label": None,
    }


def _label(position, text="obj", node_name="node_a"):
    return {
        "type": "label",
        "node_name": node_name,
        "position": position,
        "text": text,
        "font_size": 14,
        "color": "#ffffff",
        "background_color": "#000000cc",
        "scale": 1.0,
    }


def _plane(center, normal, node_name="node_a"):
    return {
        "type": "plane",
        "node_name": node_name,
        "center": center,
        "normal": normal,
        "width": 10.0,
        "height": 10.0,
        "color": "#4488ff",
        "opacity": 0.25,
    }


# ---------------------------------------------------------------------------
# aabb_iou unit tests
# ---------------------------------------------------------------------------


class TestAabbIou:
    def test_identical_boxes_returns_one(self):
        assert aabb_iou([0, 0, 0], [2, 2, 2], [0, 0, 0], [2, 2, 2]) == pytest.approx(
            1.0
        )

    def test_non_overlapping_returns_zero(self):
        assert aabb_iou([0, 0, 0], [1, 1, 1], [10, 10, 10], [1, 1, 1]) == pytest.approx(
            0.0
        )

    def test_half_overlap(self):
        # Two 2x2x2 cubes offset by 1 on x-axis → overlap 1x2x2=4, union=8+8-4=12
        iou = aabb_iou([0, 0, 0], [2, 2, 2], [1, 0, 0], [2, 2, 2])
        assert iou == pytest.approx(4 / 12)

    def test_zero_volume_returns_zero(self):
        assert aabb_iou([0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]) == pytest.approx(
            0.0
        )


# ---------------------------------------------------------------------------
# ShapeTracker tests
# ---------------------------------------------------------------------------


class TestShapeTracker:
    def test_first_frame_assigns_ids(self):
        tracker = ShapeTracker()
        shapes = [_cube([0, 0, 0], [1, 1, 1])]
        result = tracker.stabilize(shapes)
        assert len(result) == 1
        assert result[0]["id"] != ""

    def test_same_cube_keeps_id_across_frames(self):
        tracker = ShapeTracker()
        cube = _cube([0, 0, 0], [2, 2, 2])
        first = tracker.stabilize([cube])
        stable_id = first[0]["id"]
        second = tracker.stabilize([dict(cube)])
        assert second[0]["id"] == stable_id

    def test_slightly_shifted_cube_keeps_id(self):
        """IoU > 0.3 → same object."""
        tracker = ShapeTracker()
        cube1 = _cube([0, 0, 0], [2, 2, 2])
        cube2 = _cube([0.2, 0.1, 0.0], [2, 2, 2])  # small shift, high IoU
        first = tracker.stabilize([cube1])
        stable_id = first[0]["id"]
        second = tracker.stabilize([cube2])
        assert second[0]["id"] == stable_id

    def test_far_shifted_cube_gets_new_id(self):
        """IoU < 0.3 → different object."""
        tracker = ShapeTracker()
        cube1 = _cube([0, 0, 0], [1, 1, 1])
        cube2 = _cube([10, 10, 10], [1, 1, 1])
        first = tracker.stabilize([cube1])
        stable_id = first[0]["id"]
        second = tracker.stabilize([cube2])
        assert second[0]["id"] != stable_id

    def test_label_within_2m_keeps_id(self):
        tracker = ShapeTracker()
        lbl1 = _label([1.0, 2.0, 3.0])
        lbl2 = _label([1.5, 2.0, 3.0])  # 0.5 m shift
        first = tracker.stabilize([lbl1])
        stable_id = first[0]["id"]
        second = tracker.stabilize([lbl2])
        assert second[0]["id"] == stable_id

    def test_label_beyond_2m_gets_new_id(self):
        tracker = ShapeTracker()
        lbl1 = _label([0.0, 0.0, 0.0])
        lbl2 = _label([3.0, 0.0, 0.0])  # 3.0 m shift
        first = tracker.stabilize([lbl1])
        stable_id = first[0]["id"]
        second = tracker.stabilize([lbl2])
        assert second[0]["id"] != stable_id

    def test_plane_within_2m_keeps_id(self):
        tracker = ShapeTracker()
        p1 = _plane([0.0, 0.0, 0.0], [0, 0, 1])
        p2 = _plane([0.5, 0.5, 0.0], [0, 0, 1])
        first = tracker.stabilize([p1])
        stable_id = first[0]["id"]
        second = tracker.stabilize([p2])
        assert second[0]["id"] == stable_id

    def test_greedy_matching_two_cubes(self):
        """Two cubes that swap positions should still match correctly."""
        tracker = ShapeTracker()
        c1 = _cube([0, 0, 0], [2, 2, 2])
        c2 = _cube([5, 5, 5], [2, 2, 2])
        first = tracker.stabilize([c1, c2])
        id1 = next(s["id"] for s in first if s["center"] == [0, 0, 0])
        id2 = next(s["id"] for s in first if s["center"] == [5, 5, 5])

        # Same positions again — should keep same IDs
        second = tracker.stabilize([dict(c1), dict(c2)])
        id1_v2 = next(s["id"] for s in second if s["center"] == [0, 0, 0])
        id2_v2 = next(s["id"] for s in second if s["center"] == [5, 5, 5])
        assert id1_v2 == id1
        assert id2_v2 == id2

    def test_cube_does_not_match_label(self):
        """Cross-type matching must be forbidden."""
        tracker = ShapeTracker()
        cube = _cube([0, 0, 0], [1, 1, 1])
        first = tracker.stabilize([cube])
        cube_id = first[0]["id"]

        # Next frame: same position but label type
        lbl = _label([0, 0, 0])
        second = tracker.stabilize([lbl])
        assert second[0]["id"] != cube_id

    def test_different_node_name_no_match(self):
        """Shapes from different nodes must not match."""
        tracker = ShapeTracker()
        c1 = _cube([0, 0, 0], [2, 2, 2], node_name="node_a")
        first = tracker.stabilize([c1])
        stable_id = first[0]["id"]

        c2 = _cube([0, 0, 0], [2, 2, 2], node_name="node_b")
        second = tracker.stabilize([c2])
        assert second[0]["id"] != stable_id

    def test_multiple_frames_stable(self):
        """ID must remain stable over many frames with tiny jitter."""
        tracker = ShapeTracker()
        import random

        rng = random.Random(42)
        cube = _cube([0.0, 0.0, 0.0], [2.0, 2.0, 2.0])
        first = tracker.stabilize([cube])
        stable_id = first[0]["id"]
        for _ in range(20):
            jitter = [rng.uniform(-0.05, 0.05) for _ in range(3)]
            noisy = _cube(
                [cube["center"][i] + jitter[i] for i in range(3)],
                cube["size"],
            )
            result = tracker.stabilize([noisy])
            assert result[0]["id"] == stable_id

    def test_new_shape_gets_unique_id(self):
        """Two brand-new shapes in the same frame have distinct IDs."""
        tracker = ShapeTracker()
        c1 = _cube([0, 0, 0], [1, 1, 1])
        c2 = _cube([10, 10, 10], [1, 1, 1])
        result = tracker.stabilize([c1, c2])
        assert result[0]["id"] != result[1]["id"]
