"""
Unit tests for binary protocol module - binary LIDR format encoding/decoding.
"""
import struct

import numpy as np
import pytest

from app.services.lidar.protocol.binary import (
    pack_points_binary,
    unpack_points_binary,
    MAGIC_BYTES,
    VERSION
)


class TestPackPointsBinary:
    """Tests for pack_points_binary function"""
    
    def test_basic_packing(self):
        """Test basic point cloud packing"""
        points = np.array([
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0]
        ], dtype=np.float32)
        timestamp = 1234567890.123
        
        data = pack_points_binary(points, timestamp)
        
        # Check header size (20 bytes) + points (2 * 12 bytes)
        assert len(data) == 20 + 2 * 12
        
        # Verify magic bytes
        assert data[:4] == MAGIC_BYTES
    
    def test_empty_points(self):
        """Test packing empty point cloud"""
        points = np.array([]).reshape(0, 3).astype(np.float32)
        timestamp = 1234567890.0
        
        data = pack_points_binary(points, timestamp)
        
        # Should only have header (20 bytes)
        assert len(data) == 20
        
        # Unpack header to verify count is 0
        magic, version, ts, count = struct.unpack('<4sIdI', data[:20])
        assert count == 0
    
    def test_single_point(self):
        """Test packing single point"""
        points = np.array([[1.5, 2.5, 3.5]], dtype=np.float32)
        timestamp = 1000.0
        
        data = pack_points_binary(points, timestamp)
        
        # Header (20) + 1 point (12)
        assert len(data) == 32
    
    def test_header_format(self):
        """Test header structure"""
        points = np.array([[1, 2, 3]], dtype=np.float32)
        timestamp = 999.999
        
        data = pack_points_binary(points, timestamp)
        
        # Unpack and verify header
        magic, version, ts, count = struct.unpack('<4sIdI', data[:20])
        
        assert magic == MAGIC_BYTES
        assert version == VERSION
        assert ts == pytest.approx(timestamp)
        assert count == 1
    
    def test_points_with_extra_columns(self):
        """Test that only x,y,z columns are packed"""
        points = np.array([
            [1.0, 2.0, 3.0, 100.0],  # x, y, z, intensity
            [4.0, 5.0, 6.0, 150.0]
        ], dtype=np.float32)
        timestamp = 1000.0
        
        data = pack_points_binary(points, timestamp)
        
        # Should pack only xyz (3 floats * 4 bytes * 2 points = 24 bytes)
        assert len(data) == 20 + 24
        
        # Verify intensity is not included by unpacking
        points_data = data[20:]
        unpacked = np.frombuffer(points_data, dtype=np.float32).reshape(2, 3)
        assert unpacked.shape == (2, 3)  # Only xyz
    
    def test_large_point_cloud(self):
        """Test packing larger point cloud"""
        num_points = 10000
        points = np.random.rand(num_points, 3).astype(np.float32)
        timestamp = 1234567890.0
        
        data = pack_points_binary(points, timestamp)
        
        # Verify size
        expected_size = 20 + num_points * 12
        assert len(data) == expected_size
        
        # Verify count in header
        _, _, _, count = struct.unpack('<4sIdI', data[:20])
        assert count == num_points
    
    def test_timestamp_precision(self):
        """Test that timestamp is preserved with float64 precision"""
        points = np.array([[1, 2, 3]], dtype=np.float32)
        timestamp = 1234567890.123456789  # High precision
        
        data = pack_points_binary(points, timestamp)
        
        # Unpack timestamp
        _, _, ts, _ = struct.unpack('<4sIdI', data[:20])
        
        # float64 should preserve significant precision
        assert ts == pytest.approx(timestamp, abs=1e-9)
    
    def test_binary_format_consistency(self):
        """Test that the same input produces the same binary output"""
        points = np.array([[1, 2, 3]], dtype=np.float32)
        timestamp = 1000.0
        
        data1 = pack_points_binary(points, timestamp)
        data2 = pack_points_binary(points, timestamp)
        
        assert data1 == data2


class TestUnpackPointsBinary:
    """Tests for unpack_points_binary function"""
    
    def test_basic_unpacking(self):
        """Test basic unpacking"""
        # Create known data
        original_points = np.array([
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0]
        ], dtype=np.float32)
        original_timestamp = 1234567890.123
        
        # Pack then unpack
        data = pack_points_binary(original_points, original_timestamp)
        points, timestamp = unpack_points_binary(data)
        
        # Verify
        np.testing.assert_array_almost_equal(points, original_points)
        assert timestamp == pytest.approx(original_timestamp)
    
    def test_empty_point_cloud(self):
        """Test unpacking empty point cloud"""
        original_points = np.array([]).reshape(0, 3).astype(np.float32)
        original_timestamp = 1000.0
        
        data = pack_points_binary(original_points, original_timestamp)
        points, timestamp = unpack_points_binary(data)
        
        assert len(points) == 0
        assert points.shape == (0, 3)
        assert timestamp == pytest.approx(original_timestamp)
    
    def test_single_point(self):
        """Test unpacking single point"""
        original_points = np.array([[1.5, 2.5, 3.5]], dtype=np.float32)
        original_timestamp = 999.0
        
        data = pack_points_binary(original_points, original_timestamp)
        points, timestamp = unpack_points_binary(data)
        
        assert points.shape == (1, 3)
        np.testing.assert_array_almost_equal(points, original_points)
    
    def test_invalid_magic_bytes(self):
        """Test that invalid magic bytes raise ValueError"""
        data = b'XXXX' + struct.pack('<IdI', VERSION, 1000.0, 1) + b'\x00' * 12
        
        with pytest.raises(ValueError, match="Invalid magic bytes"):
            unpack_points_binary(data)
    
    def test_unsupported_version(self):
        """Test that unsupported version raises ValueError"""
        data = struct.pack('<4sIdI', MAGIC_BYTES, 999, 1000.0, 1) + b'\x00' * 12
        
        with pytest.raises(ValueError, match="Unsupported version"):
            unpack_points_binary(data)
    
    def test_size_mismatch(self):
        """Test that size mismatch raises ValueError"""
        # Header says 2 points, but only 1 point's data provided
        data = struct.pack('<4sIdI', MAGIC_BYTES, VERSION, 1000.0, 2) + b'\x00' * 12
        
        with pytest.raises(ValueError, match="Points data size mismatch"):
            unpack_points_binary(data)
    
    def test_malformed_header(self):
        """Test that malformed header raises struct.error"""
        data = b'LIDR' + b'\x00' * 10  # Incomplete header
        
        with pytest.raises(struct.error):
            unpack_points_binary(data)
    
    def test_roundtrip_large_cloud(self):
        """Test pack/unpack roundtrip with larger point cloud"""
        num_points = 10000
        original_points = np.random.rand(num_points, 3).astype(np.float32)
        original_timestamp = 1234567890.123456
        
        data = pack_points_binary(original_points, original_timestamp)
        points, timestamp = unpack_points_binary(data)
        
        assert points.shape == original_points.shape
        np.testing.assert_array_almost_equal(points, original_points)
        assert timestamp == pytest.approx(original_timestamp)
    
    def test_roundtrip_preserves_precision(self):
        """Test that float32 precision is preserved in roundtrip"""
        original_points = np.array([
            [1.23456789, 9.87654321, 5.55555555]
        ], dtype=np.float32)
        timestamp = 1000.0
        
        data = pack_points_binary(original_points, timestamp)
        points, _ = unpack_points_binary(data)
        
        # Should match float32 precision
        np.testing.assert_array_almost_equal(points, original_points, decimal=6)
    
    def test_output_dtype(self):
        """Test that output dtype is float32"""
        points_in = np.array([[1, 2, 3]], dtype=np.float32)
        timestamp = 1000.0
        
        data = pack_points_binary(points_in, timestamp)
        points_out, _ = unpack_points_binary(data)
        
        assert points_out.dtype == np.float32
    
    def test_output_shape(self):
        """Test that output shape is always (N, 3)"""
        points_in = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32)
        timestamp = 1000.0
        
        data = pack_points_binary(points_in, timestamp)
        points_out, _ = unpack_points_binary(data)
        
        assert points_out.shape == (2, 3)


class TestProtocolConstants:
    """Tests for protocol constants"""
    
    def test_magic_bytes(self):
        """Test magic bytes constant"""
        assert MAGIC_BYTES == b'LIDR'
        assert len(MAGIC_BYTES) == 4
    
    def test_version(self):
        """Test version constant"""
        assert VERSION == 1
        assert isinstance(VERSION, int)
