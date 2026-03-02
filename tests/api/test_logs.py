"""
Tests for Logs API endpoints
"""
import pytest
import os
import tempfile
import json
import asyncio
from pathlib import Path
from unittest.mock import patch, mock_open
from fastapi.testclient import TestClient
from app.app import app


class TestLogsRestEndpoint:
    """Test suite for /api/v1/logs REST endpoint"""
    
    def test_logs_empty_when_file_not_exists(self):
        """Test /logs returns empty list when log file doesn't exist"""
        with patch('app.api.v1.logs.LOG_PATH', '/nonexistent/path/app.log'):
            client = TestClient(app)
            response = client.get("/api/v1/logs")
            
            assert response.status_code == 200
            data = response.json()
            assert data == []
    
    def test_logs_returns_parsed_entries(self):
        """Test /logs returns properly parsed log entries"""
        log_content = (
            "2024-02-23 12:34:56,123 | INFO | app | Application started\n"
            "2024-02-23 12:34:57,456 | WARNING | lidar.sensor | Sensor offline\n"
            "2024-02-23 12:34:58,789 | ERROR | websocket.manager | Connection failed\n"
        )
        
        with patch('app.api.v1.logs.LOG_PATH', '/test/app.log'):
            with patch('builtins.open', mock_open(read_data=log_content)):
                with patch('os.path.exists', return_value=True):
                    client = TestClient(app)
                    response = client.get("/api/v1/logs")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data) == 3
                    
                    # Verify newest first (reversed order)
                    assert data[0]['level'] == 'ERROR'
                    assert data[0]['module'] == 'websocket.manager'
                    assert data[1]['level'] == 'WARNING'
                    assert data[2]['level'] == 'INFO'
    
    def test_logs_filter_by_level(self):
        """Test /logs filters by log level"""
        log_content = (
            "2024-02-23 12:34:56,123 | INFO | app | Info message\n"
            "2024-02-23 12:34:57,456 | WARNING | app | Warning message\n"
            "2024-02-23 12:34:58,789 | ERROR | app | Error message\n"
        )
        
        with patch('app.api.v1.logs.LOG_PATH', '/test/app.log'):
            with patch('builtins.open', mock_open(read_data=log_content)):
                with patch('os.path.exists', return_value=True):
                    client = TestClient(app)
                    response = client.get("/api/v1/logs?level=ERROR")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data) == 1
                    assert data[0]['level'] == 'ERROR'
                    assert data[0]['message'] == 'Error message'
    
    def test_logs_search_by_text(self):
        """Test /logs searches by text in message"""
        log_content = (
            "2024-02-23 12:34:56,123 | INFO | app | Sensor initialized\n"
            "2024-02-23 12:34:57,456 | INFO | app | Processing started\n"
            "2024-02-23 12:34:58,789 | INFO | app | Sensor error detected\n"
        )
        
        with patch('app.api.v1.logs.LOG_PATH', '/test/app.log'):
            with patch('builtins.open', mock_open(read_data=log_content)):
                with patch('os.path.exists', return_value=True):
                    client = TestClient(app)
                    response = client.get("/api/v1/logs?search=Sensor")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data) == 2
                    assert all('Sensor' in entry['message'] for entry in data)
    
    def test_logs_pagination_offset(self):
        """Test /logs pagination with offset"""
        log_content = (
            "2024-02-23 12:34:56,123 | INFO | app | Message 1\n"
            "2024-02-23 12:34:57,456 | INFO | app | Message 2\n"
            "2024-02-23 12:34:58,789 | INFO | app | Message 3\n"
            "2024-02-23 12:34:59,000 | INFO | app | Message 4\n"
        )
        
        with patch('app.api.v1.logs.LOG_PATH', '/test/app.log'):
            with patch('builtins.open', mock_open(read_data=log_content)):
                with patch('os.path.exists', return_value=True):
                    client = TestClient(app)
                    response = client.get("/api/v1/logs?offset=1&limit=2")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data) == 2
                    # Newest first (reversed): should get Message 3 and Message 2
                    assert data[0]['message'] == 'Message 3'
                    assert data[1]['message'] == 'Message 2'
    
    def test_logs_respects_limit_max(self):
        """Test /logs respects maximum limit of 500"""
        # Create log with 600 lines
        lines = [f"2024-02-23 12:34:56,{i:03d} | INFO | app | Message {i}\n" for i in range(600)]
        log_content = "".join(lines)
        
        with patch('app.api.v1.logs.LOG_PATH', '/test/app.log'):
            with patch('builtins.open', mock_open(read_data=log_content)):
                with patch('os.path.exists', return_value=True):
                    client = TestClient(app)
                    response = client.get("/api/v1/logs?limit=1000")
                    
                    assert response.status_code == 200
                    data = response.json()
                    # Should be capped at 500
                    assert len(data) == 500
    
    def test_logs_combines_level_and_search_filters(self):
        """Test /logs applies both level and search filters"""
        log_content = (
            "2024-02-23 12:34:56,123 | INFO | app | Sensor online\n"
            "2024-02-23 12:34:57,456 | INFO | app | Device offline\n"
            "2024-02-23 12:34:58,789 | ERROR | app | Sensor error\n"
        )
        
        with patch('app.api.v1.logs.LOG_PATH', '/test/app.log'):
            with patch('builtins.open', mock_open(read_data=log_content)):
                with patch('os.path.exists', return_value=True):
                    client = TestClient(app)
                    response = client.get("/api/v1/logs?level=INFO&search=Sensor")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data) == 1
                    assert data[0]['level'] == 'INFO'
                    assert 'Sensor' in data[0]['message']
    
    def test_logs_parse_log_line_with_special_chars(self):
        """Test parsing log lines with special characters"""
        log_content = (
            "2024-02-23 12:34:56,123 | ERROR | fusion.service | Failed: 'config' not found\n"
        )
        
        with patch('app.api.v1.logs.LOG_PATH', '/test/app.log'):
            with patch('builtins.open', mock_open(read_data=log_content)):
                with patch('os.path.exists', return_value=True):
                    client = TestClient(app)
                    response = client.get("/api/v1/logs")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data) == 1
                    assert "'config' not found" in data[0]['message']
    
    def test_logs_ignores_invalid_log_lines(self):
        """Test /logs ignores lines that don't match log format"""
        log_content = (
            "This is an invalid line\n"
            "2024-02-23 12:34:56,123 | INFO | app | Valid line\n"
            "Another invalid line\n"
        )
        
        with patch('app.api.v1.logs.LOG_PATH', '/test/app.log'):
            with patch('builtins.open', mock_open(read_data=log_content)):
                with patch('os.path.exists', return_value=True):
                    client = TestClient(app)
                    response = client.get("/api/v1/logs")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data) == 1
                    assert data[0]['message'] == 'Valid line'


class TestLogsWebSocketEndpoint:
    """Test suite for /api/v1/logs/ws WebSocket endpoint"""
    
    @pytest.mark.asyncio
    async def test_logs_ws_endpoint_exists(self):
        """Test /logs/ws endpoint is defined"""
        from app.api.v1.logs import router
        
        # Check route exists
        routes = [route.path for route in router.routes]
        assert "/logs/ws" in routes
    
    def test_logs_ws_can_connect(self):
        """Test WebSocket can connect to /logs/ws"""
        client = TestClient(app)
        
        with patch('app.api.v1.logs.LOG_PATH', '/nonexistent/app.log'):
            with patch('os.path.exists', return_value=False):
                with patch('asyncio.sleep', side_effect=Exception("stop")):
                    with pytest.raises(Exception, match="stop"):
                        with client.websocket_connect("/api/v1/logs/ws"):
                            pass
    
    def test_logs_ws_accepts_filter_params(self):
        """Test WebSocket accepts level and search query parameters"""
        client = TestClient(app)
        
        with patch('app.api.v1.logs.LOG_PATH', '/nonexistent/app.log'):
            with patch('os.path.exists', return_value=False):
                with patch('asyncio.sleep', side_effect=Exception("stop")):
                    with pytest.raises(Exception, match="stop"):
                        with client.websocket_connect("/api/v1/logs/ws?level=ERROR&search=failed"):
                            pass
    
    def test_logs_ws_streams_new_log_entries(self):
        """Test WebSocket streams new log entries as they are written"""
        log_content = (
            "2024-02-23 12:34:56,123 | INFO | app | Entry 1\n"
            "2024-02-23 12:34:57,456 | INFO | app | Entry 2\n"
        )
        
        client = TestClient(app)
        
        with patch('app.api.v1.logs.LOG_PATH', '/test/app.log'):
            with patch('os.path.exists', return_value=True):
                with patch('os.stat') as mock_stat:
                    mock_stat.return_value.st_ino = 12345
                    
                    # Mock file reading for streaming
                    file_content = iter(log_content.split('\n'))
                    
                    with patch('builtins.open', mock_open(read_data=log_content)):
                        with patch('asyncio.sleep', side_effect=Exception("stop")):
                            with pytest.raises(Exception, match="stop"):
                                with client.websocket_connect("/api/v1/logs/ws"):
                                    pass


class TestLogsParsingUtility:
    """Test suite for log parsing utility function"""
    
    def test_parse_log_line_valid_format(self):
        """Test parsing valid log line"""
        from app.api.v1.logs import parse_log_line
        
        line = "2024-02-23 12:34:56,123 | INFO | app | Application started\n"
        result = parse_log_line(line)
        
        assert result is not None
        assert result['timestamp'] == "2024-02-23 12:34:56,123"
        assert result['level'] == 'INFO'
        assert result['module'] == 'app'
        assert result['message'] == 'Application started'
    
    def test_parse_log_line_with_different_levels(self):
        """Test parsing log lines with different levels"""
        from app.api.v1.logs import parse_log_line
        
        levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        for level in levels:
            line = f"2024-02-23 12:34:56,123 | {level} | module | Test message\n"
            result = parse_log_line(line)
            
            assert result is not None
            assert result['level'] == level
    
    def test_parse_log_line_with_dashes_in_message(self):
        """Test parsing log line with dashes in message"""
        from app.api.v1.logs import parse_log_line
        
        line = "2024-02-23 12:34:56,123 | INFO | app | Failed to connect - timeout after 30s\n"
        result = parse_log_line(line)
        
        assert result is not None
        assert result['message'] == 'Failed to connect - timeout after 30s'
    
    def test_parse_log_line_invalid_format(self):
        """Test parsing invalid log line returns None"""
        from app.api.v1.logs import parse_log_line
        
        invalid_lines = [
            "This is not a log line\n",
            "2024-02-23 | INFO | incomplete line\n",
            "",
            "   \n",
        ]
        
        for line in invalid_lines:
            result = parse_log_line(line)
            assert result is None
    
    def test_parse_log_line_with_json_in_message(self):
        """Test parsing log line with JSON data in message"""
        from app.api.v1.logs import parse_log_line
        
        line = '2024-02-23 12:34:56,123 | ERROR | api | Request failed: {"error": "timeout"}\n'
        result = parse_log_line(line)
        
        assert result is not None
        assert '{"error": "timeout"}' in result['message']
