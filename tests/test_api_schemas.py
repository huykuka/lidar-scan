"""Tests for API schema models.

This module tests all Pydantic schema models defined in app/api/v1/schemas/.
Following TDD principles, these tests validate the schema implementations.
"""

import pytest
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, ValidationError
import json

from app.api.v1.schemas.common import StatusResponse, UpsertResponse, DeleteEdgeResponse
from app.api.v1.schemas.nodes import NodeRecord, NodeStatusItem, NodesStatusResponse
from app.api.v1.schemas.edges import EdgeRecord
from app.api.v1.schemas.system import SystemStatusResponse, SystemControlResponse
from app.api.v1.schemas.config import ImportSummary, ImportResponse, ConfigValidationSummary, ValidationResponse
from app.api.v1.schemas.logs import LogEntry
from app.api.v1.schemas.calibration import (
    CalibrationResult, CalibrationTriggerResponse, AcceptResponse, 
    RollbackResponse, CalibrationRecord, CalibrationHistoryResponse, CalibrationStatsResponse
)


class TestCommonSchemas:
    """Test shared response schemas in common.py"""

    def test_status_response_creation(self):
        """StatusResponse should accept status field"""
        response = StatusResponse(status="success")
        assert response.status == "success"
        
    def test_status_response_validation(self):
        """StatusResponse should validate required fields"""
        with pytest.raises(ValidationError):
            StatusResponse()  # Missing required 'status' field
        
    def test_upsert_response_creation(self):
        """UpsertResponse should accept status and id fields"""
        response = UpsertResponse(status="success", id="test-uuid")
        assert response.status == "success"
        assert response.id == "test-uuid"
        
    def test_delete_edge_response_creation(self):
        """DeleteEdgeResponse should accept status and id fields"""
        response = DeleteEdgeResponse(status="deleted", id="edge-uuid")
        assert response.status == "deleted"
        assert response.id == "edge-uuid"


class TestNodeSchemas:
    """Test node-related schemas in nodes.py"""

    def test_node_record_creation(self):
        """NodeRecord should accept all required fields"""
        node = NodeRecord(
            id="test-uuid",
            name="Test Node",
            type="sensor",
            category="sensor",
            enabled=True
        )
        assert node.id == "test-uuid"
        assert node.name == "Test Node"
        assert node.type == "sensor"
        assert node.category == "sensor"
        assert node.enabled is True
        assert node.config == {}  # default empty dict
        assert node.x is None  # optional field
        assert node.y is None  # optional field
        
    def test_node_record_optional_fields(self):
        """NodeRecord should handle optional x, y coordinates"""
        node = NodeRecord(
            id="test-uuid",
            name="Test Node",
            type="sensor", 
            category="sensor",
            enabled=True,
            x=100.0,
            y=200.0
        )
        assert node.x == 100.0
        assert node.y == 200.0
        
    def test_node_record_config_dict(self):
        """NodeRecord should accept arbitrary config dict"""
        config = {"lidar_type": "multiscan", "hostname": "192.168.1.10"}
        node = NodeRecord(
            id="test-uuid",
            name="Test Node",
            type="sensor",
            category="sensor", 
            enabled=True,
            config=config
        )
        assert node.config == config
        
    def test_node_record_example_config(self):
        """NodeRecord should have proper model_config with example"""
        # Test that the schema has examples in its model_config
        config = NodeRecord.model_config
        assert 'json_schema_extra' in config
        assert 'examples' in config['json_schema_extra']
        examples = config['json_schema_extra']['examples']
        assert len(examples) >= 1  # At least one example
        # First example should be a sensor
        sensor_example = examples[0]
        assert 'lidar_type' in sensor_example['config']

    def test_node_status_item_creation(self):
        """NodeStatusItem should accept all fields with proper defaults"""
        item = NodeStatusItem(
            node_id="test-uuid",
            name="Test Node",
            type="sensor",
            category="sensor",
            enabled=True,
            operational_state="RUNNING",
        )
        assert item.throttle_ms == 0.0  # default
        assert item.throttled_count == 0  # default
        assert item.topic is None  # optional
        assert item.application_state is None  # optional
        assert item.error_message is None  # optional
        
    def test_node_status_item_throttle_defaults(self):
        """NodeStatusItem should have correct throttle defaults"""
        item = NodeStatusItem(
            node_id="test-uuid",
            name="Test Node", 
            type="sensor",
            category="sensor",
            enabled=True,
            operational_state="STOPPED",
            throttle_ms=100.0,
            throttled_count=5
        )
        assert item.throttle_ms == 100.0
        assert item.throttled_count == 5
        
    def test_nodes_status_response_creation(self):
        """NodesStatusResponse should wrap list of NodeStatusItem"""
        items = [
            NodeStatusItem(
                node_id="test-uuid-1",
                name="Node 1",
                type="sensor",
                category="sensor", 
                enabled=True,
                operational_state="RUNNING",
            ),
            NodeStatusItem(
                node_id="test-uuid-2",
                name="Node 2",
                type="fusion",
                category="fusion",
                enabled=True, 
                operational_state="STOPPED",
            )
        ]
        response = NodesStatusResponse(nodes=items)
        assert len(response.nodes) == 2
        assert response.nodes[0].node_id == "test-uuid-1"
        assert response.nodes[1].node_id == "test-uuid-2"


class TestEdgeSchemas:
    """Test edge-related schemas in edges.py"""

    def test_edge_record_creation(self):
        """EdgeRecord should accept all port connection fields"""
        edge = EdgeRecord(
            id="edge-uuid",
            source_node="source-uuid", 
            source_port="out",
            target_node="target-uuid",
            target_port="in"
        )
        assert edge.id == "edge-uuid"
        assert edge.source_node == "source-uuid"
        assert edge.source_port == "out"
        assert edge.target_node == "target-uuid"
        assert edge.target_port == "in"
        
    def test_edge_record_validation(self):
        """EdgeRecord should validate required fields"""
        with pytest.raises(ValidationError):
            EdgeRecord(id="edge-uuid")  # Missing required fields


class TestSystemSchemas:
    """Test system-related schemas in system.py"""

    def test_system_status_response_creation(self):
        """SystemStatusResponse should accept status fields"""
        response = SystemStatusResponse(
            is_running=True,
            active_sensors=["sensor-1", "sensor-2"],
            version="1.3.0"
        )
        assert response.is_running is True
        assert response.active_sensors == ["sensor-1", "sensor-2"]
        assert response.version == "1.3.0"
        
    def test_system_status_response_active_sensors_list(self):
        """SystemStatusResponse should accept list of sensor IDs"""
        response = SystemStatusResponse(
            is_running=False,
            active_sensors=[],
            version="1.3.0"
        )
        assert response.active_sensors == []
        
    def test_system_control_response_creation(self):
        """SystemControlResponse should accept status and is_running"""
        response = SystemControlResponse(status="success", is_running=True)
        assert response.status == "success"
        assert response.is_running is True


class TestConfigSchemas:
    """Test configuration-related schemas in config.py"""

    def test_import_summary_creation(self):
        """ImportSummary should accept nodes and edges counts"""
        summary = ImportSummary(nodes=5, edges=3)
        assert summary.nodes == 5
        assert summary.edges == 3
        
    def test_import_response_creation(self):
        """ImportResponse should accept all import result fields"""
        summary = ImportSummary(nodes=2, edges=1)
        response = ImportResponse(
            success=True,
            mode="replace",
            imported=summary,
            node_ids=["uuid1", "uuid2"],
            reloaded=True
        )
        assert response.success is True
        assert response.mode == "replace"
        assert response.imported.nodes == 2
        assert response.imported.edges == 1
        assert response.node_ids == ["uuid1", "uuid2"]
        assert response.reloaded is True
        
    def test_config_validation_summary_creation(self):
        """ConfigValidationSummary should accept validation counts"""
        summary = ConfigValidationSummary(nodes=3, edges=2)
        assert summary.nodes == 3
        assert summary.edges == 2
        
    def test_validation_response_creation(self):
        """ValidationResponse should accept validation results"""
        summary = ConfigValidationSummary(nodes=2, edges=1)
        response = ValidationResponse(
            valid=True,
            errors=[],
            warnings=["Warning message"],
            summary=summary
        )
        assert response.valid is True
        assert response.errors == []
        assert response.warnings == ["Warning message"]
        assert response.summary.nodes == 2


class TestLogSchemas:
    """Test log-related schemas in logs.py"""

    def test_log_entry_creation(self):
        """LogEntry should accept timestamp, level, module, message"""
        entry = LogEntry(
            timestamp="2025-01-01 12:00:00",
            level="INFO",
            module="app.services.nodes.orchestrator", 
            message="Config reload complete."
        )
        assert entry.timestamp == "2025-01-01 12:00:00"
        assert entry.level == "INFO"
        assert entry.module == "app.services.nodes.orchestrator"
        assert entry.message == "Config reload complete."
        
    def test_log_entry_validation(self):
        """LogEntry should validate required fields"""
        with pytest.raises(ValidationError):
            LogEntry(timestamp="2025-01-01", level="INFO")  # Missing module and message


class TestCalibrationSchemas:
    """Test calibration-related schemas in calibration.py"""

    def test_calibration_result_creation(self):
        """CalibrationResult should accept fitness, rmse, quality"""
        result = CalibrationResult(
            fitness=0.94,
            rmse=0.012,
            quality="good"
        )
        assert result.fitness == 0.94
        assert result.rmse == 0.012
        assert result.quality == "good"
        
    def test_calibration_result_optional_fields(self):
        """CalibrationResult should handle optional fitness/rmse"""
        result = CalibrationResult()
        assert result.fitness is None
        assert result.rmse is None
        assert result.quality is None
        
    def test_calibration_trigger_response_creation(self):
        """CalibrationTriggerResponse should accept results dict"""
        results = {
            "sensor-1": CalibrationResult(fitness=0.94, rmse=0.012, quality="good"),
            "sensor-2": CalibrationResult(fitness=0.87, rmse=0.021, quality="acceptable")
        }
        response = CalibrationTriggerResponse(
            success=True,
            results=results,
            pending_approval=True
        )
        assert response.success is True
        assert len(response.results) == 2
        assert response.pending_approval is True
        assert response.results["sensor-1"].fitness == 0.94
        
    def test_accept_response_creation(self):
        """AcceptResponse should accept success and accepted list"""
        response = AcceptResponse(success=True, accepted=["sensor-1", "sensor-2"])
        assert response.success is True
        assert response.accepted == ["sensor-1", "sensor-2"]
        
    def test_rollback_response_creation(self):
        """RollbackResponse should accept success, sensor_id, restored_to"""
        response = RollbackResponse(
            success=True,
            sensor_id="sensor-uuid",
            restored_to="2025-01-01T12:00:00Z"
        )
        assert response.success is True
        assert response.sensor_id == "sensor-uuid"
        assert response.restored_to == "2025-01-01T12:00:00Z"
        
    def test_calibration_record_creation(self):
        """CalibrationRecord should accept all calibration history fields"""
        record = CalibrationRecord(
            id="cal-uuid",
            sensor_id="sensor-uuid",
            timestamp="2025-01-01T12:00:00Z",
            accepted=True,
            fitness=0.94,
            rmse=0.012
        )
        assert record.id == "cal-uuid"
        assert record.sensor_id == "sensor-uuid"
        assert record.timestamp == "2025-01-01T12:00:00Z"
        assert record.accepted is True
        assert record.fitness == 0.94
        assert record.rmse == 0.012
        
    def test_calibration_history_response_creation(self):
        """CalibrationHistoryResponse should wrap sensor_id and history"""
        records = [
            CalibrationRecord(
                id="cal-1",
                sensor_id="sensor-uuid",
                timestamp="2025-01-01T12:00:00Z",
                accepted=True
            ),
            CalibrationRecord(
                id="cal-2", 
                sensor_id="sensor-uuid",
                timestamp="2025-01-01T11:00:00Z",
                accepted=False
            )
        ]
        response = CalibrationHistoryResponse(
            sensor_id="sensor-uuid",
            history=records
        )
        assert response.sensor_id == "sensor-uuid"
        assert len(response.history) == 2
        assert response.history[0].accepted is True
        assert response.history[1].accepted is False
        
    def test_calibration_stats_response_creation(self):
        """CalibrationStatsResponse should accept all statistics fields"""
        response = CalibrationStatsResponse(
            sensor_id="sensor-uuid",
            total_attempts=12,
            accepted_count=8,
            avg_fitness=0.91,
            avg_rmse=0.018
        )
        assert response.sensor_id == "sensor-uuid"
        assert response.total_attempts == 12
        assert response.accepted_count == 8
        assert response.avg_fitness == 0.91
        assert response.avg_rmse == 0.018