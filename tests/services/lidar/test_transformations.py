"""
Unit tests for transformations module - transformation and mathematical utilities.
"""
import numpy as np
import pytest

from app.services.modules.lidar.core.transformations import (
    create_transformation_matrix,
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
