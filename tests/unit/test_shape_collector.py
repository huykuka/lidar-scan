"""Unit tests for ShapeCollectorMixin (BE-02)."""
import pytest


class TestShapeCollectorMixin:
    def test_init_empty_pending(self):
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        mixin = ShapeCollectorMixin()
        assert mixin._pending_shapes == []

    def test_emit_shape_appends(self):
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        from app.services.nodes.shapes import CubeShape
        mixin = ShapeCollectorMixin()
        shape = CubeShape(center=[1, 2, 3], size=[1, 1, 1])
        mixin.emit_shape(shape)
        assert len(mixin._pending_shapes) == 1

    def test_collect_and_clear_returns_copy(self):
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        from app.services.nodes.shapes import CubeShape
        mixin = ShapeCollectorMixin()
        shape = CubeShape(center=[1, 2, 3], size=[1, 1, 1])
        mixin.emit_shape(shape)
        result = mixin.collect_and_clear_shapes()
        assert len(result) == 1
        assert result[0] is shape

    def test_collect_clears_pending(self):
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        from app.services.nodes.shapes import LabelShape
        mixin = ShapeCollectorMixin()
        mixin.emit_shape(LabelShape(position=[0, 0, 0], text="hi"))
        mixin.collect_and_clear_shapes()
        assert mixin._pending_shapes == []

    def test_multiple_shapes(self):
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        from app.services.nodes.shapes import CubeShape, PlaneShape, LabelShape
        mixin = ShapeCollectorMixin()
        mixin.emit_shape(CubeShape(center=[1, 2, 3], size=[1, 1, 1]))
        mixin.emit_shape(PlaneShape(center=[0, 0, 0], normal=[0, 0, 1]))
        mixin.emit_shape(LabelShape(position=[0, 0, 0], text="x"))
        result = mixin.collect_and_clear_shapes()
        assert len(result) == 3
        assert mixin._pending_shapes == []

    def test_collect_empty_returns_empty(self):
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        mixin = ShapeCollectorMixin()
        result = mixin.collect_and_clear_shapes()
        assert result == []

    def test_second_collect_empty_after_first(self):
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        from app.services.nodes.shapes import LabelShape
        mixin = ShapeCollectorMixin()
        mixin.emit_shape(LabelShape(position=[1, 2, 3], text="x"))
        mixin.collect_and_clear_shapes()
        assert mixin.collect_and_clear_shapes() == []
