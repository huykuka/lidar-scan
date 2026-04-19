"""Unit tests for shape Pydantic models and ID hashing (BE-01, BE-03)."""
import pytest
from pydantic import ValidationError


class TestCubeShape:
    def test_valid_cube(self):
        from app.services.nodes.shapes import CubeShape
        shape = CubeShape(center=[1.0, 2.0, 3.0], size=[0.5, 0.5, 0.5])
        assert shape.type == "cube"
        assert shape.color == "#00ff00"
        assert shape.opacity == 0.4
        assert shape.wireframe is True
        assert shape.label is None
        assert shape.rotation == [0.0, 0.0, 0.0]

    def test_cube_extra_fields_forbidden(self):
        from app.services.nodes.shapes import CubeShape
        with pytest.raises(ValidationError):
            CubeShape(center=[1.0, 2.0, 3.0], size=[0.5, 0.5, 0.5], unknown_field="bad")

    def test_cube_missing_required(self):
        from app.services.nodes.shapes import CubeShape
        with pytest.raises(ValidationError):
            CubeShape(center=[1.0, 2.0, 3.0])  # missing size

    def test_cube_with_label(self):
        from app.services.nodes.shapes import CubeShape
        shape = CubeShape(center=[0, 0, 0], size=[1, 1, 1], label="test")
        assert shape.label == "test"

    def test_cube_model_dump(self):
        from app.services.nodes.shapes import CubeShape
        shape = CubeShape(center=[1.2, 0.5, 0.3], size=[0.8, 0.6, 1.2], color="#ff0000")
        d = shape.model_dump()
        assert d["type"] == "cube"
        assert d["center"] == [1.2, 0.5, 0.3]
        assert d["color"] == "#ff0000"


class TestPlaneShape:
    def test_valid_plane(self):
        from app.services.nodes.shapes import PlaneShape
        shape = PlaneShape(center=[0.0, 0.0, 0.0], normal=[0.0, 0.0, 1.0])
        assert shape.type == "plane"
        assert shape.width == 10.0
        assert shape.height == 10.0
        assert shape.color == "#4488ff"
        assert shape.opacity == 0.25

    def test_plane_extra_fields_forbidden(self):
        from app.services.nodes.shapes import PlaneShape
        with pytest.raises(ValidationError):
            PlaneShape(center=[0, 0, 0], normal=[0, 0, 1], bad_field=1)

    def test_plane_missing_required(self):
        from app.services.nodes.shapes import PlaneShape
        with pytest.raises(ValidationError):
            PlaneShape(center=[0, 0, 0])  # missing normal


class TestLabelShape:
    def test_valid_label(self):
        from app.services.nodes.shapes import LabelShape
        shape = LabelShape(position=[1.0, 2.0, 3.0], text="hello")
        assert shape.type == "label"
        assert shape.font_size == 14
        assert shape.color == "#ffffff"
        assert shape.background_color == "#000000cc"
        assert shape.scale == 1.0

    def test_label_extra_fields_forbidden(self):
        from app.services.nodes.shapes import LabelShape
        with pytest.raises(ValidationError):
            LabelShape(position=[0, 0, 0], text="hi", extra=1)

    def test_label_missing_text(self):
        from app.services.nodes.shapes import LabelShape
        with pytest.raises(ValidationError):
            LabelShape(position=[0, 0, 0])


class TestShapeFrame:
    def test_empty_frame(self):
        from app.services.nodes.shapes import ShapeFrame
        frame = ShapeFrame(timestamp=1713523800.123, shapes=[])
        d = frame.model_dump()
        assert d["timestamp"] == 1713523800.123
        assert d["shapes"] == []

    def test_frame_with_all_shape_types(self):
        from app.services.nodes.shapes import ShapeFrame, CubeShape, PlaneShape, LabelShape
        frame = ShapeFrame(
            timestamp=1713523800.341,
            shapes=[
                CubeShape(center=[1.2, 0.5, 0.3], size=[0.8, 0.6, 1.2]),
                PlaneShape(center=[0, 0, -0.05], normal=[0, 0, 1]),
                LabelShape(position=[1.2, 0.5, 1.5], text="hello"),
            ]
        )
        d = frame.model_dump()
        assert len(d["shapes"]) == 3
        types = [s["type"] for s in d["shapes"]]
        assert "cube" in types
        assert "plane" in types
        assert "label" in types

    def test_frame_serializes_correctly(self):
        """Validate against the api-spec.md §5 example payload."""
        from app.services.nodes.shapes import ShapeFrame, CubeShape, PlaneShape, LabelShape
        frame = ShapeFrame(
            timestamp=1713523800.341,
            shapes=[
                CubeShape(
                    id="a3f9c21b88d41e02",
                    node_name="Cluster Detector",
                    center=[1.2, 0.5, 0.3],
                    size=[0.8, 0.6, 1.2],
                    rotation=[0.0, 0.0, 0.0],
                    color="#00ff00",
                    opacity=0.4,
                    wireframe=True,
                    label="Person (conf: 0.91)",
                ),
            ]
        )
        d = frame.model_dump()
        s = d["shapes"][0]
        assert s["id"] == "a3f9c21b88d41e02"
        assert s["node_name"] == "Cluster Detector"
        assert s["label"] == "Person (conf: 0.91)"


class TestComputeShapeId:
    def test_cube_id_stable(self):
        from app.services.nodes.shapes import CubeShape, compute_shape_id
        shape = CubeShape(center=[1.0, 2.0, 3.0], size=[0.5, 0.5, 0.5])
        id1 = compute_shape_id("node-abc", shape)
        id2 = compute_shape_id("node-abc", shape)
        assert id1 == id2

    def test_cube_id_is_16_chars(self):
        from app.services.nodes.shapes import CubeShape, compute_shape_id
        shape = CubeShape(center=[1.0, 2.0, 3.0], size=[0.5, 0.5, 0.5])
        assert len(compute_shape_id("node-abc", shape)) == 16

    def test_different_geometry_different_id(self):
        from app.services.nodes.shapes import CubeShape, compute_shape_id
        s1 = CubeShape(center=[1.0, 2.0, 3.0], size=[0.5, 0.5, 0.5])
        s2 = CubeShape(center=[1.0, 2.0, 4.0], size=[0.5, 0.5, 0.5])
        assert compute_shape_id("node-abc", s1) != compute_shape_id("node-abc", s2)

    def test_different_node_id_different_id(self):
        from app.services.nodes.shapes import CubeShape, compute_shape_id
        shape = CubeShape(center=[1.0, 2.0, 3.0], size=[0.5, 0.5, 0.5])
        assert compute_shape_id("node-A", shape) != compute_shape_id("node-B", shape)

    def test_plane_id_stable(self):
        from app.services.nodes.shapes import PlaneShape, compute_shape_id
        shape = PlaneShape(center=[0, 0, 0], normal=[0, 0, 1])
        assert compute_shape_id("n1", shape) == compute_shape_id("n1", shape)

    def test_label_id_stable(self):
        from app.services.nodes.shapes import LabelShape, compute_shape_id
        shape = LabelShape(position=[1, 2, 3], text="hello")
        assert compute_shape_id("n1", shape) == compute_shape_id("n1", shape)

    def test_label_different_text_different_id(self):
        from app.services.nodes.shapes import LabelShape, compute_shape_id
        s1 = LabelShape(position=[1, 2, 3], text="hello")
        s2 = LabelShape(position=[1, 2, 3], text="world")
        assert compute_shape_id("n1", s1) != compute_shape_id("n1", s2)

    def test_id_is_hex_string(self):
        from app.services.nodes.shapes import CubeShape, compute_shape_id
        shape = CubeShape(center=[1, 2, 3], size=[1, 1, 1])
        result = compute_shape_id("node", shape)
        int(result, 16)  # should not raise — must be valid hex
