"""
Tests for standardized node status Pydantic schemas.

Spec: .opencode/plans/node-status-standardization/api-spec.md § 1.1
"""
import pytest
import time
from pydantic import ValidationError

from app.schemas.status import (
    OperationalState,
    ApplicationState,
    NodeStatusUpdate,
    SystemStatusBroadcast,
)


class TestOperationalStateEnum:
    """Test the OperationalState enum has exactly 4 values."""

    def test_has_exactly_four_states(self):
        """OperationalState must have exactly: INITIALIZE, RUNNING, STOPPED, ERROR."""
        assert set(OperationalState) == {
            OperationalState.INITIALIZE,
            OperationalState.RUNNING,
            OperationalState.STOPPED,
            OperationalState.ERROR,
        }

    def test_state_values_are_strings(self):
        """Each state value should be uppercase string matching its name."""
        assert OperationalState.INITIALIZE.value == "INITIALIZE"
        assert OperationalState.RUNNING.value == "RUNNING"
        assert OperationalState.STOPPED.value == "STOPPED"
        assert OperationalState.ERROR.value == "ERROR"


class TestApplicationState:
    """Test ApplicationState model accepts valid JSON-serializable types."""

    def test_accepts_string_value(self):
        """ApplicationState.value should accept string."""
        state = ApplicationState(label="connection_status", value="connected", color="green")
        assert state.label == "connection_status"
        assert state.value == "connected"
        assert state.color == "green"

    def test_accepts_bool_value(self):
        """ApplicationState.value should accept boolean."""
        state = ApplicationState(label="calibrating", value=True, color="blue")
        assert state.label == "calibrating"
        assert state.value is True
        assert state.color == "blue"

    def test_accepts_int_value(self):
        """ApplicationState.value should accept integer."""
        state = ApplicationState(label="fusing", value=3, color="blue")
        assert state.label == "fusing"
        assert state.value == 3
        assert state.color == "blue"

    def test_accepts_float_value(self):
        """ApplicationState.value should accept float."""
        state = ApplicationState(label="threshold", value=0.5, color="gray")
        assert state.label == "threshold"
        assert state.value == 0.5
        assert state.color == "gray"

    def test_color_is_optional(self):
        """ApplicationState.color should be optional."""
        state = ApplicationState(label="condition", value="true")
        assert state.color is None


class TestNodeStatusUpdate:
    """Test NodeStatusUpdate requires node_id, operational_state, timestamp."""

    def test_requires_node_id_and_operational_state(self):
        """NodeStatusUpdate requires node_id and operational_state at minimum."""
        status = NodeStatusUpdate(
            node_id="test_node_123",
            operational_state=OperationalState.RUNNING,
        )
        assert status.node_id == "test_node_123"
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is None
        assert status.error_message is None
        assert isinstance(status.timestamp, float)

    def test_timestamp_defaults_to_current_time(self):
        """NodeStatusUpdate.timestamp should default to current Unix epoch."""
        before = time.time()
        status = NodeStatusUpdate(
            node_id="test_node",
            operational_state=OperationalState.RUNNING,
        )
        after = time.time()
        assert before <= status.timestamp <= after

    def test_application_state_is_optional(self):
        """application_state should default to None."""
        status = NodeStatusUpdate(
            node_id="test_node",
            operational_state=OperationalState.RUNNING,
        )
        assert status.application_state is None

    def test_error_message_is_optional(self):
        """error_message should default to None."""
        status = NodeStatusUpdate(
            node_id="test_node",
            operational_state=OperationalState.RUNNING,
        )
        assert status.error_message is None

    def test_operational_state_error_with_no_error_message_is_valid(self):
        """
        NodeStatusUpdate with operational_state=ERROR and no error_message 
        should still be valid (relaxed constraint per spec).
        """
        status = NodeStatusUpdate(
            node_id="test_node",
            operational_state=OperationalState.ERROR,
        )
        assert status.operational_state == OperationalState.ERROR
        assert status.error_message is None

    def test_rejects_invalid_operational_state(self):
        """Pydantic should reject operational_state='UNKNOWN' with ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            NodeStatusUpdate(
                node_id="test_node",
                operational_state="UNKNOWN",  # type: ignore
            )
        errors = exc_info.value.errors()
        assert any("operational_state" in str(e) for e in errors)

    def test_with_application_state(self):
        """NodeStatusUpdate should correctly embed ApplicationState."""
        app_state = ApplicationState(
            label="connection_status",
            value="connected",
            color="green",
        )
        status = NodeStatusUpdate(
            node_id="lidar_sensor_abc",
            operational_state=OperationalState.RUNNING,
            application_state=app_state,
        )
        assert status.application_state.label == "connection_status"
        assert status.application_state.value == "connected"
        assert status.application_state.color == "green"

    def test_with_error_message(self):
        """NodeStatusUpdate should accept error_message for ERROR state."""
        status = NodeStatusUpdate(
            node_id="test_node",
            operational_state=OperationalState.ERROR,
            error_message="UDP socket timeout after 5s",
        )
        assert status.error_message == "UDP socket timeout after 5s"


class TestSystemStatusBroadcast:
    """Test SystemStatusBroadcast serialises to JSON without numpy or binary types."""

    def test_serializes_to_json(self):
        """SystemStatusBroadcast.nodes should serialise to JSON cleanly."""
        status1 = NodeStatusUpdate(
            node_id="node_1",
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="connection_status",
                value="connected",
                color="green",
            ),
        )
        status2 = NodeStatusUpdate(
            node_id="node_2",
            operational_state=OperationalState.ERROR,
            error_message="Open3D: invalid point cloud",
        )
        broadcast = SystemStatusBroadcast(nodes=[status1, status2])
        
        # Pydantic v2 uses model_dump()
        json_dict = broadcast.model_dump()
        
        assert "nodes" in json_dict
        assert len(json_dict["nodes"]) == 2
        assert json_dict["nodes"][0]["node_id"] == "node_1"
        assert json_dict["nodes"][0]["operational_state"] == "RUNNING"
        assert json_dict["nodes"][1]["node_id"] == "node_2"
        assert json_dict["nodes"][1]["operational_state"] == "ERROR"

    def test_empty_nodes_list_is_valid(self):
        """SystemStatusBroadcast with empty nodes list should be valid."""
        broadcast = SystemStatusBroadcast(nodes=[])
        assert broadcast.nodes == []

    def test_enum_values_serialized_as_strings(self):
        """OperationalState enum should serialize as string value, not enum object."""
        status = NodeStatusUpdate(
            node_id="test",
            operational_state=OperationalState.INITIALIZE,
        )
        broadcast = SystemStatusBroadcast(nodes=[status])
        json_dict = broadcast.model_dump()
        
        # Enum should be serialized as string "INITIALIZE", not enum
        assert json_dict["nodes"][0]["operational_state"] == "INITIALIZE"
        assert isinstance(json_dict["nodes"][0]["operational_state"], str)
