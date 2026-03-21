"""
B-15: Unit tests for the canonical Pose Pydantic model.

Tests cover:
- Valid construction with all six fields
- Default construction (all zeros)
- Boundary values for roll/pitch/yaw (±180)
- NaN rejection
- Pose.zero() classmethod
- to_flat_dict() method
- Frozen model (assignment raises ValidationError)
"""
import math
import pytest
from pydantic import ValidationError


class TestPoseConstruction:
    """B-15: Valid construction tests"""

    def test_valid_full_construction(self):
        from app.schemas.pose import Pose
        p = Pose(x=1.0, y=2.0, z=3.0, roll=10.0, pitch=-20.0, yaw=45.0)
        assert p.x == 1.0
        assert p.y == 2.0
        assert p.z == 3.0
        assert p.roll == 10.0
        assert p.pitch == -20.0
        assert p.yaw == 45.0

    def test_default_construction_all_zeros(self):
        from app.schemas.pose import Pose
        p = Pose()
        assert p.x == 0.0
        assert p.y == 0.0
        assert p.z == 0.0
        assert p.roll == 0.0
        assert p.pitch == 0.0
        assert p.yaw == 0.0

    def test_partial_construction_defaults_zero(self):
        from app.schemas.pose import Pose
        p = Pose(x=100.0, yaw=45.0)
        assert p.x == 100.0
        assert p.y == 0.0
        assert p.z == 0.0
        assert p.roll == 0.0
        assert p.pitch == 0.0
        assert p.yaw == 45.0


class TestPoseBoundaries:
    """B-15: Boundary value tests for angle fields"""

    def test_roll_boundary_180_passes(self):
        from app.schemas.pose import Pose
        p = Pose(roll=180.0)
        assert p.roll == 180.0

    def test_roll_boundary_neg180_passes(self):
        from app.schemas.pose import Pose
        p = Pose(roll=-180.0)
        assert p.roll == -180.0

    def test_roll_exceeds_180_raises(self):
        from app.schemas.pose import Pose
        with pytest.raises(ValidationError):
            Pose(roll=180.001)

    def test_roll_below_neg180_raises(self):
        from app.schemas.pose import Pose
        with pytest.raises(ValidationError):
            Pose(roll=-180.001)

    def test_pitch_boundary_180_passes(self):
        from app.schemas.pose import Pose
        p = Pose(pitch=180.0)
        assert p.pitch == 180.0

    def test_pitch_boundary_neg180_passes(self):
        from app.schemas.pose import Pose
        p = Pose(pitch=-180.0)
        assert p.pitch == -180.0

    def test_pitch_exceeds_180_raises(self):
        from app.schemas.pose import Pose
        with pytest.raises(ValidationError):
            Pose(pitch=180.001)

    def test_pitch_below_neg180_raises(self):
        from app.schemas.pose import Pose
        with pytest.raises(ValidationError):
            Pose(pitch=-180.001)

    def test_yaw_boundary_180_passes(self):
        from app.schemas.pose import Pose
        p = Pose(yaw=180.0)
        assert p.yaw == 180.0

    def test_yaw_boundary_neg180_passes(self):
        from app.schemas.pose import Pose
        p = Pose(yaw=-180.0)
        assert p.yaw == -180.0

    def test_yaw_exceeds_270_raises(self):
        from app.schemas.pose import Pose
        with pytest.raises(ValidationError):
            Pose(yaw=270.0)

    def test_yaw_below_neg180_raises(self):
        from app.schemas.pose import Pose
        with pytest.raises(ValidationError):
            Pose(yaw=-180.001)

    def test_xyz_large_values_pass(self):
        """Position fields have no range constraint."""
        from app.schemas.pose import Pose
        p = Pose(x=999999.0, y=-999999.0, z=0.0)
        assert p.x == 999999.0


class TestPoseNaNRejection:
    """B-15: NaN and Inf rejection"""

    def test_nan_x_raises(self):
        from app.schemas.pose import Pose
        with pytest.raises(ValidationError):
            Pose(x=float('nan'))

    def test_inf_y_raises(self):
        from app.schemas.pose import Pose
        with pytest.raises(ValidationError):
            Pose(y=float('inf'))

    def test_neg_inf_z_raises(self):
        from app.schemas.pose import Pose
        with pytest.raises(ValidationError):
            Pose(z=float('-inf'))

    def test_nan_roll_raises(self):
        from app.schemas.pose import Pose
        with pytest.raises(ValidationError):
            Pose(roll=float('nan'))


class TestPoseZeroClassmethod:
    """B-15: Pose.zero() classmethod"""

    def test_zero_returns_pose_instance(self):
        from app.schemas.pose import Pose
        p = Pose.zero()
        assert isinstance(p, Pose)

    def test_zero_all_fields_are_zero(self):
        from app.schemas.pose import Pose
        p = Pose.zero()
        assert p.x == 0.0
        assert p.y == 0.0
        assert p.z == 0.0
        assert p.roll == 0.0
        assert p.pitch == 0.0
        assert p.yaw == 0.0

    def test_zero_equals_default_construction(self):
        from app.schemas.pose import Pose
        assert Pose.zero() == Pose()


class TestPoseToFlatDict:
    """B-15: to_flat_dict() method"""

    def test_to_flat_dict_returns_correct_dict(self):
        from app.schemas.pose import Pose
        p = Pose(x=1.0, y=2.0, z=3.0, roll=10.0, pitch=20.0, yaw=30.0)
        d = p.to_flat_dict()
        assert d == {"x": 1.0, "y": 2.0, "z": 3.0, "roll": 10.0, "pitch": 20.0, "yaw": 30.0}

    def test_to_flat_dict_zero_pose(self):
        from app.schemas.pose import Pose
        d = Pose.zero().to_flat_dict()
        assert d == {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}

    def test_to_flat_dict_returns_dict_not_model(self):
        from app.schemas.pose import Pose
        d = Pose(x=5.0).to_flat_dict()
        assert isinstance(d, dict)

    def test_to_flat_dict_has_all_six_keys(self):
        from app.schemas.pose import Pose
        d = Pose().to_flat_dict()
        assert set(d.keys()) == {"x", "y", "z", "roll", "pitch", "yaw"}


class TestPoseFrozen:
    """B-15: Frozen model — assignment raises ValidationError"""

    def test_assignment_raises_validation_error(self):
        from app.schemas.pose import Pose
        p = Pose(x=1.0)
        with pytest.raises((ValidationError, TypeError)):
            p.x = 99.0

    def test_frozen_model_is_hashable(self):
        from app.schemas.pose import Pose
        p = Pose(x=1.0, yaw=45.0)
        # Frozen Pydantic models are hashable
        assert hash(p) is not None


class TestPoseSchemaExport:
    """B-02: Importable from app.schemas"""

    def test_importable_from_app_schemas(self):
        from app.schemas import Pose  # noqa: F401
        assert Pose is not None

    def test_importable_directly_from_pose_module(self):
        from app.schemas.pose import Pose  # noqa: F401
        assert Pose is not None
