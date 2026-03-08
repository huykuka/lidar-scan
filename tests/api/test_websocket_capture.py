"""
Tests for WebSocket capture API functionality
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import HTTPException
from app.api.v1.websocket import router


class TestWebSocketCapture:
    """Test suite for WebSocket capture API"""
    
    @pytest.mark.asyncio
    @patch('app.api.v1.websocket.manager')
    async def test_capture_frame_returns_503_on_topic_removal(self, mock_manager):
        """Test capture_frame returns 503 when topic is removed during wait"""
        # Setup manager.wait_for_next to raise CancelledError
        mock_manager.wait_for_next = AsyncMock(side_effect=asyncio.CancelledError())
        
        # Import the function to test directly
        from app.api.v1.websocket import capture_frame
        
        # Call should raise HTTPException with 503 status
        with pytest.raises(HTTPException) as exc_info:
            await capture_frame("test_topic")
        
        assert exc_info.value.status_code == 503
        assert "Topic was removed while waiting for frame. Please retry." in str(exc_info.value.detail)
    
    @pytest.mark.asyncio 
    @patch('app.api.v1.websocket.manager')
    async def test_capture_frame_returns_504_on_timeout(self, mock_manager):
        """Test capture_frame returns 504 on timeout (existing behavior)"""
        # Setup manager.wait_for_next to raise TimeoutError
        mock_manager.wait_for_next = AsyncMock(side_effect=asyncio.TimeoutError())
        
        # Import the function to test directly
        from app.api.v1.websocket import capture_frame
        
        # Call should raise HTTPException with 504 status
        with pytest.raises(HTTPException) as exc_info:
            await capture_frame("test_topic")
        
        assert exc_info.value.status_code == 504
        assert "Timeout waiting for frame" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    @patch('app.api.v1.websocket.manager')
    async def test_capture_frame_success_returns_data(self, mock_manager):
        """Test capture_frame successfully returns data on success"""
        # Setup manager.wait_for_next to return mock data
        test_data = b"test_binary_data"
        mock_manager.wait_for_next = AsyncMock(return_value=test_data)
        
        # Import the function to test directly
        from app.api.v1.websocket import capture_frame
        
        # Call should return Response with binary data
        response = await capture_frame("test_topic")
        
        assert response.body == test_data
        assert response.media_type == "application/octet-stream"
    
    @pytest.mark.asyncio
    @patch('app.api.v1.websocket.manager')
    async def test_capture_frame_concurrent_cancellation_scenario(self, mock_manager):
        """Test realistic scenario where topic is removed while wait_for_next is pending"""
        
        # This simulates the real-world scenario described in the technical spec:
        # 1. HTTP request calls wait_for_next() 
        # 2. Concurrently, a reload_config() is called
        # 3. reload_config() calls unregister_topic() which cancels pending futures
        # 4. wait_for_next() receives CancelledError
        # 5. capture_frame() should convert this to HTTP 503
        
        # Mock wait_for_next to raise CancelledError after a short delay
        async def mock_wait_for_next(topic, timeout=None):
            await asyncio.sleep(0.1)
            raise asyncio.CancelledError("Future was cancelled by unregister_topic")
        
        mock_manager.wait_for_next = AsyncMock(side_effect=mock_wait_for_next)
        
        # Import the function to test directly
        from app.api.v1.websocket import capture_frame
        
        # The capture should raise HTTPException with 503
        with pytest.raises(HTTPException) as exc_info:
            await capture_frame("test_topic")
        
        assert exc_info.value.status_code == 503
        assert "Topic was removed while waiting for frame. Please retry." in str(exc_info.value.detail)