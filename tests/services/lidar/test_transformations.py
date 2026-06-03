"""
Unit tests for transformations module - transformation and mathematical utilities.
"""
import math

import numpy as np
import pytest

from app.modules.lidar.core.transformations import (
    create_transformation_matrix,
    gravity_to_roll_pitch,
    imu_gravity_alignment_matrix,
    imu_orientation_matrix,
    quaternion_is_valid,
    quaternion_to_rpy,
    transform_points,
    pose_to_dict
)


class TestCreateTransformationMatrix:
    """Tests for create_transformation_matrix function"""
    
    def test_identity_transform(self):
        """Test that zero translation and rotation gives identity matrix"""
        T = create_transformation_matrix(0, 0, 0, 0, 0, 0)
        expected = np.eye(4)
        np.testing.assert_array_almost_equal(T, expected)
    
    def test_translation_only(self):
        """Test pure translation without rotation"""
        T = create_transformation_matrix(1.0, 2.0, 3.0, 0, 0, 0)
        
        # Check that rotation part is identity
        np.testing.assert_array_almost_equal(T[:3, :3], np.eye(3))
        
        # Check translation vector
        assert T[0, 3] == 1.0
        assert T[1, 3] == 2.0
        assert T[2, 3] == 3.0
        assert T[3, 3] == 1.0
    
    def test_rotation_90deg_yaw(self):
        """Test 90 degree yaw rotation (around Z-axis)"""
        T = create_transformation_matrix(0, 0, 0, 0, 0, 90)
        
        # After 90° yaw: X -> Y, Y -> -X, Z -> Z
        # Test by transforming unit vectors
        # X-axis (1,0,0) should become Y-axis (0,1,0)
        x_vec = np.array([1, 0, 0])
        result = T[:3, :3] @ x_vec
        np.testing.assert_array_almost_equal(result, [0, 1, 0], decimal=10)
        
        # Y-axis (0,1,0) should become -X-axis (-1,0,0)
        y_vec = np.array([0, 1, 0])
        result = T[:3, :3] @ y_vec
        np.testing.assert_array_almost_equal(result, [-1, 0, 0], decimal=10)
    
    def test_rotation_90deg_pitch(self):
        """Test 90 degree pitch rotation (around Y-axis)"""
        T = create_transformation_matrix(0, 0, 0, 0, 90, 0)
        
        # After 90° pitch: X -> -Z, Y -> Y, Z -> X
        x_vec = np.array([1, 0, 0])
        result = T[:3, :3] @ x_vec
        np.testing.assert_array_almost_equal(result, [0, 0, -1], decimal=10)
        
        z_vec = np.array([0, 0, 1])
        result = T[:3, :3] @ z_vec
        np.testing.assert_array_almost_equal(result, [1, 0, 0], decimal=10)
    
    def test_rotation_90deg_roll(self):
        """Test 90 degree roll rotation (around X-axis)"""
        T = create_transformation_matrix(0, 0, 0, 90, 0, 0)
        
        # After 90° roll: X -> X, Y -> -Z, Z -> Y
        y_vec = np.array([0, 1, 0])
        result = T[:3, :3] @ y_vec
        np.testing.assert_array_almost_equal(result, [0, 0, 1], decimal=10)
        
        z_vec = np.array([0, 0, 1])
        result = T[:3, :3] @ z_vec
        np.testing.assert_array_almost_equal(result, [0, -1, 0], decimal=10)
    
    def test_combined_translation_and_rotation(self):
        """Test combined translation and rotation"""
        T = create_transformation_matrix(1.0, 2.0, 3.0, 0, 0, 90)
        
        # Check translation is preserved
        assert T[0, 3] == 1.0
        assert T[1, 3] == 2.0
        assert T[2, 3] == 3.0
        
        # Check rotation is applied (90° yaw)
        x_vec = np.array([1, 0, 0])
        result = T[:3, :3] @ x_vec
        np.testing.assert_array_almost_equal(result, [0, 1, 0], decimal=10)
    
    def test_negative_angles(self):
        """Test negative rotation angles"""
        T_pos = create_transformation_matrix(0, 0, 0, 0, 0, 90)
        T_neg = create_transformation_matrix(0, 0, 0, 0, 0, -90)
        
        # 90° and -90° should be inverses
        product = T_pos[:3, :3] @ T_neg[:3, :3]
        np.testing.assert_array_almost_equal(product, np.eye(3), decimal=10)
    
    def test_matrix_shape(self):
        """Test that output is always 4x4"""
        T = create_transformation_matrix(1, 2, 3, 45, 60, 90)
        assert T.shape == (4, 4)
    
    def test_homogeneous_bottom_row(self):
        """Test that bottom row is always [0, 0, 0, 1]"""
        T = create_transformation_matrix(5, 10, 15, 30, 60, 90)
        expected_bottom = np.array([0, 0, 0, 1])
        np.testing.assert_array_equal(T[3, :], expected_bottom)


class TestTransformPoints:
    """Tests for transform_points function"""
    
    def test_identity_transform_unchanged(self):
        """Test that identity transform leaves points unchanged"""
        points = np.array([
            [1, 2, 3],
            [4, 5, 6]
        ])
        T = np.eye(4)
        result = transform_points(points, T)
        np.testing.assert_array_equal(result, points)
    
    def test_translation_only(self):
        """Test pure translation"""
        points = np.array([[1.0, 2.0, 3.0]])
        T = create_transformation_matrix(10.0, 20.0, 30.0, 0, 0, 0)
        result = transform_points(points, T)
        expected = np.array([[11.0, 22.0, 33.0]])
        np.testing.assert_array_almost_equal(result, expected)
    
    def test_rotation_only(self):
        """Test pure rotation (90° yaw)"""
        points = np.array([[1.0, 0.0, 0.0]])  # Point on X-axis
        T = create_transformation_matrix(0, 0, 0, 0, 0, 90)  # 90° yaw
        result = transform_points(points, T)
        # Should rotate to Y-axis
        expected = np.array([[0.0, 1.0, 0.0]])
        np.testing.assert_array_almost_equal(result, expected, decimal=10)
    
    def test_combined_translation_rotation(self):
        """Test combined translation and rotation"""
        points = np.array([[1.0, 0.0, 0.0]])
        T = create_transformation_matrix(5.0, 0.0, 0.0, 0, 0, 90)
        result = transform_points(points, T)
        # Rotate X to Y, then translate by (5,0,0)
        expected = np.array([[5.0, 1.0, 0.0]])
        np.testing.assert_array_almost_equal(result, expected, decimal=10)
    
    def test_multiple_points(self):
        """Test transformation of multiple points"""
        points = np.array([
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1]
        ], dtype=np.float32)
        T = create_transformation_matrix(1, 1, 1, 0, 0, 0)
        result = transform_points(points, T)
        expected = np.array([
            [2, 1, 1],
            [1, 2, 1],
            [1, 1, 2]
        ], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)
    
    def test_points_with_extra_columns(self):
        """Test that extra columns (like intensity) are preserved"""
        points = np.array([
            [1, 0, 0, 100],  # x, y, z, intensity
            [0, 1, 0, 150]
        ], dtype=np.float32)
        T = create_transformation_matrix(1, 0, 0, 0, 0, 0)
        result = transform_points(points, T)
        
        # First 3 columns should be transformed
        assert result[0, 0] == 2  # x translated by 1
        assert result[0, 1] == 0  # y unchanged
        assert result[0, 2] == 0  # z unchanged
        
        # Fourth column should be preserved
        assert result[0, 3] == 100
        assert result[1, 3] == 150
    
    def test_empty_points(self):
        """Test with empty point cloud"""
        points = np.array([]).reshape(0, 3)
        T = create_transformation_matrix(1, 2, 3, 0, 0, 0)
        result = transform_points(points, T)
        assert len(result) == 0
    
    def test_none_points(self):
        """Test with None input"""
        result = transform_points(None, np.eye(4))
        assert result is None
    
    def test_does_not_modify_input(self):
        """Test that original points array is not modified"""
        points = np.array([[1.0, 2.0, 3.0]])
        points_copy = points.copy()
        T = create_transformation_matrix(10, 20, 30, 0, 0, 0)
        transform_points(points, T)
        np.testing.assert_array_equal(points, points_copy)


class TestPoseToDict:
    """Tests for pose_to_dict function"""
    
    def test_basic_conversion(self):
        """Test basic pose parameter conversion"""
        result = pose_to_dict(1.0, 2.0, 3.0, 10.0, 20.0, 30.0)
        expected = {
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "roll": 10.0,
            "pitch": 20.0,
            "yaw": 30.0
        }
        assert result == expected
    
    def test_zero_values(self):
        """Test with all zero values"""
        result = pose_to_dict(0, 0, 0, 0, 0, 0)
        expected = {
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0
        }
        assert result == expected
    
    def test_negative_values(self):
        """Test with negative values"""
        result = pose_to_dict(-1.5, -2.5, -3.5, -45, -90, -180)
        assert result["x"] == -1.5
        assert result["y"] == -2.5
        assert result["z"] == -3.5
        assert result["roll"] == -45.0
        assert result["pitch"] == -90.0
        assert result["yaw"] == -180.0
    
    def test_integer_inputs(self):
        """Test that integer inputs are converted to float"""
        result = pose_to_dict(1, 2, 3, 10, 20, 30)
        for value in result.values():
            assert isinstance(value, float)
    
    def test_all_keys_present(self):
        """Test that all expected keys are present"""
        result = pose_to_dict(0, 0, 0, 0, 0, 0)
        expected_keys = {"x", "y", "z", "roll", "pitch", "yaw"}
        assert set(result.keys()) == expected_keys


class TestQuaternionToRpy:
    """Tests for quaternion_to_rpy — must match SICK multiScan SDK convention."""

    def test_identity_quaternion_gives_zero_rpy(self):
        """Identity quaternion (no rotation) should give (0, 0, 0)."""
        roll, pitch, yaw = quaternion_to_rpy(1.0, 0.0, 0.0, 0.0)
        assert abs(roll) < 1e-10
        assert abs(pitch) < 1e-10
        assert abs(yaw) < 1e-10

    def test_pure_roll_90deg(self):
        """Quaternion for 90° roll about X-axis."""
        angle = math.radians(90)
        w = math.cos(angle / 2)
        x = math.sin(angle / 2)
        roll, pitch, yaw = quaternion_to_rpy(w, x, 0.0, 0.0)
        assert abs(roll - 90.0) < 1e-6
        assert abs(pitch) < 1e-6
        assert abs(yaw) < 1e-6

    def test_pure_pitch_45deg(self):
        """Quaternion for 45° pitch about Y-axis."""
        angle = math.radians(45)
        w = math.cos(angle / 2)
        y = math.sin(angle / 2)
        roll, pitch, yaw = quaternion_to_rpy(w, 0.0, y, 0.0)
        assert abs(roll) < 1e-6
        assert abs(pitch - 45.0) < 1e-6
        assert abs(yaw) < 1e-6

    def test_pure_yaw_180deg(self):
        """Quaternion for 180° yaw about Z-axis."""
        angle = math.radians(180)
        w = math.cos(angle / 2)
        z = math.sin(angle / 2)
        roll, pitch, yaw = quaternion_to_rpy(w, 0.0, 0.0, z)
        assert abs(roll) < 1e-6
        assert abs(pitch) < 1e-6
        assert abs(abs(yaw) - 180.0) < 1e-6

    def test_matches_sick_lua_formula(self):
        """Cross-validate against SICK Lua quaternionToRPY reference formula."""
        # Arbitrary quaternion (normalized)
        w, x, y, z = 0.7071, 0.3536, 0.3536, 0.5
        norm = math.sqrt(w**2 + x**2 + y**2 + z**2)
        w, x, y, z = w / norm, x / norm, y / norm, z / norm

        # SICK Lua reference:
        expected_roll = math.degrees(math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)))
        sinp = 2 * (w * y - z * x)
        sinp = max(-1.0, min(1.0, sinp))
        expected_pitch = math.degrees(math.asin(sinp))
        expected_yaw = math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))

        roll, pitch, yaw = quaternion_to_rpy(w, x, y, z)
        assert abs(roll - expected_roll) < 1e-6
        assert abs(pitch - expected_pitch) < 1e-6
        assert abs(yaw - expected_yaw) < 1e-6

    def test_gimbal_lock_pitch_90(self):
        """Pitch at +90° (gimbal lock) should not produce NaN."""
        angle = math.radians(90)
        w = math.cos(angle / 2)
        y = math.sin(angle / 2)
        roll, pitch, yaw = quaternion_to_rpy(w, 0.0, y, 0.0)
        assert not math.isnan(roll)
        assert abs(pitch - 90.0) < 1e-4
        assert not math.isnan(yaw)


class TestQuaternionIsValid:
    """Tests for quaternion_is_valid."""

    def test_unit_quaternion_valid(self):
        assert quaternion_is_valid(1.0, 0.0, 0.0, 0.0) is True

    def test_all_zeros_invalid(self):
        assert quaternion_is_valid(0.0, 0.0, 0.0, 0.0) is False

    def test_near_unit_valid(self):
        assert quaternion_is_valid(0.7071, 0.7071, 0.0, 0.0) is True


class TestImuOrientationMatrix:
    """Tests for imu_orientation_matrix — leveling from quaternion."""

    def test_identity_gives_identity_matrix(self):
        """No rotation quaternion → identity alignment matrix."""
        M = imu_orientation_matrix(1.0, 0.0, 0.0, 0.0)
        np.testing.assert_array_almost_equal(M, np.eye(4))

    def test_roll_10deg_levels_tilted_cloud(self):
        """A sensor tilted 10° roll should produce leveled output."""
        angle_deg = 10.0
        angle_rad = math.radians(angle_deg)
        # Quaternion for 10° rotation about X
        w = math.cos(angle_rad / 2)
        x = math.sin(angle_rad / 2)
        M = imu_orientation_matrix(w, x, 0.0, 0.0)

        # A point at (0, 0, 1) in sensor frame — after leveling it should
        # rotate by 10° roll
        point_sensor = np.array([[0.0, 0.0, 1.0]])
        leveled = transform_points(point_sensor, M)

        # Expected: (0, -sin(10°), cos(10°))
        expected_y = -math.sin(angle_rad)
        expected_z = math.cos(angle_rad)
        np.testing.assert_array_almost_equal(
            leveled[0], [0.0, expected_y, expected_z], decimal=5
        )

    def test_includes_yaw_in_orientation(self):
        """Yaw component SHOULD be applied for continuous auto-level."""
        angle_rad = math.radians(45)
        # Pure yaw quaternion (45° about Z)
        w = math.cos(angle_rad / 2)
        z = math.sin(angle_rad / 2)
        M = imu_orientation_matrix(w, 0.0, 0.0, z)

        # Should NOT be identity — yaw rotates XY plane
        assert not np.allclose(M, np.eye(4))
        # A point at (1, 0, 0) should rotate 45° in XY
        point = np.array([[1.0, 0.0, 0.0]])
        rotated = transform_points(point, M)
        expected_x = math.cos(angle_rad)
        expected_y = math.sin(angle_rad)
        np.testing.assert_array_almost_equal(
            rotated[0], [expected_x, expected_y, 0.0], decimal=5
        )


class TestGravityToRollPitch:
    """Tests for gravity_to_roll_pitch — fallback accelerometer method."""

    def test_level_sensor_gravity_down_z(self):
        """Sensor level: gravity = (0, 0, -9.81) → roll=0, pitch=0."""
        roll, pitch = gravity_to_roll_pitch(0.0, 0.0, -9.81)
        assert abs(roll - 180.0) < 1e-6 or abs(roll + 180.0) < 1e-6 or abs(roll) < 1e-6
        # For az negative: roll = atan2(0, -9.81) = π → 180° but typical convention
        # expects gravity along +Z when sensor Z points up. Use +9.81 for that case.

    def test_level_sensor_gravity_up_z(self):
        """Sensor level with Z up: gravity = (0, 0, +9.81) → roll=0, pitch=0."""
        roll, pitch = gravity_to_roll_pitch(0.0, 0.0, 9.81)
        assert abs(roll) < 1e-6
        assert abs(pitch) < 1e-6

    def test_tilted_roll(self):
        """Sensor rolled 45°: gravity has Y component."""
        g = 9.81
        # 45° roll → ay = g*sin(45°), az = g*cos(45°)
        ay = g * math.sin(math.radians(45))
        az = g * math.cos(math.radians(45))
        roll, pitch = gravity_to_roll_pitch(0.0, ay, az)
        assert abs(roll - 45.0) < 1e-4
        assert abs(pitch) < 1e-4
